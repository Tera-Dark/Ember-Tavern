package engine

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestRuntimeProfilePreservesLegacyAndDoesNotLeak(t *testing.T) {
	m := testManager(t)
	i, _ := m.Create("profile", "main", 0, false)
	if e := m.SaveSettings(i.ID, map[string]string{"DECISION_API_KEY": "legacy-qa-secret", "DECISION_MODEL": "old"}); e != nil {
		t.Fatal(e)
	}
	path := filepath.Join(m.path(i.ID), "settings.json")
	before, _ := os.ReadFile(path)
	if e := m.SetRuntimeSettings(i.ID, map[string]string{"DECISION_API_KEY": "runtime-qa-secret", "DECISION_MODEL": "new"}); e != nil {
		t.Fatal(e)
	}
	values, _ := m.Settings(i.ID)
	if values["DECISION_API_KEY"] != nil || values["DECISION_API_KEY_configured"] != true || values["DECISION_MODEL"] != "new" {
		t.Fatal("invalid projection")
	}
	if !strings.Contains(strings.Join(m.childEnv(i.ID), "\n"), "DECISION_API_KEY=runtime-qa-secret") {
		t.Fatal("overlay not injected")
	}
	if strings.Contains(m.redact(i.ID, "runtime-qa-secret"), "runtime-qa-secret") {
		t.Fatal("secret in logs")
	}
	if redacted := m.redact(i.ID, "legacy-qa-secret runtime-qa-secret"); strings.Contains(redacted, "qa-secret") {
		t.Fatal("legacy key exposed while a new profile is bound")
	}
	if e := m.SaveSettings(i.ID, map[string]string{"TTS_MODEL": "voice"}); e == nil {
		t.Fatal("overlay could leak into legacy settings")
	}
	after, _ := os.ReadFile(path)
	if string(before) != string(after) {
		t.Fatal("legacy settings changed")
	}
	if e := m.SetRuntimeSettings(i.ID, map[string]string{"DATA_DIR": "unsafe"}); e == nil {
		t.Fatal("storage override")
	}
	m.active[i.ID] = "task"
	if e := m.SetRuntimeSettings(i.ID, nil); e == nil {
		t.Fatal("changed running task settings")
	}
	delete(m.active, i.ID)
	if e := m.SetRuntimeSettings(i.ID, nil); e != nil {
		t.Fatal(e)
	}
	if m.configValues(i.ID)["DECISION_API_KEY"] != "legacy-qa-secret" {
		t.Fatal("detach did not restore legacy")
	}
	m.Close()
	restored, e := New(Config{Root: m.Root()})
	if e != nil {
		t.Fatal(e)
	}
	defer restored.Close()
	if restored.configValues(i.ID)["DECISION_MODEL"] != "old" {
		t.Fatal("runtime overlay persisted")
	}
}
