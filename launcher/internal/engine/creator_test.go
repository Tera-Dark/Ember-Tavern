package engine

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestCreatorEnvironmentAndResultsNeverPersistProviderKeysOrDraftBodies(t *testing.T) {
	m := testManager(t)
	i, e := m.Create("author", "main", 0, false)
	if e != nil {
		t.Fatal(e)
	}
	if e = m.SetRuntimeSettings(i.ID, map[string]string{"DECISION_API_KEY": "provider-qa-secret", "GEMINI_API_KEY": "knowledge-qa-secret", "TTS_API_KEY": "voice-qa-secret"}); e != nil {
		t.Fatal(e)
	}
	env := strings.Join(m.creatorEnv(i.ID), "\n")
	if strings.Contains(env, "qa-secret") {
		t.Fatal("provider credentials passed to creator")
	}
	if !strings.Contains(env, "GEMINI_API_KEY=\n") {
		t.Fatal("dotenv key import not blocked")
	}
	task := &Task{ID: ident(), InstanceID: i.ID, Kind: "creator", Status: "success", StartedAt: timestamp(), creatorResult: json.RawMessage(`{"ok":true,"private":"draft-body-only-in-memory"}`)}
	m.mu.Lock()
	m.tasks[task.ID] = task
	m.persistTaskHistoryLocked()
	m.mu.Unlock()
	history, e := os.ReadFile(filepath.Join(m.Root(), "task-history.json"))
	if e != nil {
		t.Fatal(e)
	}
	if strings.Contains(string(history), "draft-body") {
		t.Fatal("private creator result in task history")
	}
	result, e := m.CreatorResult(task.ID)
	if e != nil || result["done"] != true {
		t.Fatal("private result unavailable", e)
	}
	if _, e = m.Creator(i.ID, CreatorRequest{Operation: "shell", Directory: t.TempDir()}); e == nil {
		t.Fatal("arbitrary command accepted")
	}
}

func TestCreatorSubprocessDoesNotExecuteDraftAndFailuresDoNotBreakInstance(t *testing.T) {
	python := os.Getenv("EMBER_LAUNCHER_TEST_PYTHON")
	if python == "" {
		t.Skip("set Python for real creator subprocess")
	}
	source, e := filepath.Abs("../../..")
	if e != nil {
		t.Fatal(e)
	}
	m, e := New(Config{Root: t.TempDir(), BundledSource: source})
	if e != nil {
		t.Fatal(e)
	}
	defer m.Close()
	i, e := m.Create("author", "main", 0, false)
	if e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(filepath.Join(m.path(i.ID), "python-path"), []byte(python), 0600); e != nil {
		t.Fatal(e)
	}
	folder := filepath.Join(t.TempDir(), "draft")
	task, e := m.Creator(i.ID, CreatorRequest{Operation: "create", Directory: folder, Kind: "worldbook", Identity: "qa-go-author", Name: "Synthetic Go author"})
	if e != nil {
		t.Fatal(e)
	}
	waitTask(t, m, task, true)
	result, e := m.CreatorResult(task.ID)
	if e != nil {
		t.Fatal(e)
	}
	var created map[string]any
	if json.Unmarshal(result["result"].(json.RawMessage), &created) != nil || created["ok"] != true {
		t.Fatal("create failed")
	}
	entry := filepath.Join(folder, "worldbook.json")
	before, _ := os.ReadFile(entry)
	failed, e := m.Creator(i.ID, CreatorRequest{Operation: "metadata", Directory: folder, Revision: strings.Repeat("0", 64), Metadata: map[string]any{"name": "stale metadata"}})
	if e != nil {
		t.Fatal(e)
	}
	waitTask(t, m, failed, false)
	if m.List()[0].Error != "" {
		t.Fatal("draft validation marked the instance broken")
	}
	after, _ := os.ReadFile(entry)
	if string(before) != string(after) {
		t.Fatal("stale edit overwritten")
	}
	if last, e := os.ReadFile(filepath.Join(m.path(i.ID), "last-task.json")); e != nil || strings.Contains(string(last), "stale metadata") {
		t.Fatal("draft in last-task", e)
	}
}
