package engine

import (
	"encoding/json"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func freeTestPort(t *testing.T) int {
	t.Helper()
	l, e := net.Listen("tcp", "127.0.0.1:0")
	if e != nil {
		t.Fatal(e)
	}
	port := l.Addr().(*net.TCPAddr).Port
	l.Close()
	return port
}
func indexedManager(t *testing.T, rows ...any) (*Manager, []byte) {
	t.Helper()
	root := t.TempDir()
	b, _ := json.Marshal(map[string]any{"schema": 1, "instances": rows})
	if e := os.WriteFile(filepath.Join(root, "launcher.json"), b, 0600); e != nil {
		t.Fatal(e)
	}
	m, e := New(Config{Root: root})
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(m.Close)
	return m, b
}
func legacyRow(t *testing.T, value string) Instance {
	return Instance{ID: value, Name: "保留我的战役", Port: freeTestPort(t), Channel: "main", LAN: true}
}

func TestLegacyLoadReadOnlyAndSavePreservesQuarantine(t *testing.T) {
	valid := legacyRow(t, strings.Repeat("a", 32))
	old := map[string]any{"id": "old-room", "name": "旧档", "port": freeTestPort(t), "channel": "main", "private_extra": "do-not-return-this"}
	m, original := indexedManager(t, valid, old)
	current, _ := os.ReadFile(filepath.Join(m.Root(), "launcher.json"))
	if string(current) != string(original) || len(m.List()) != 1 {
		t.Fatal("load changed source index or valid row")
	}
	if _, e := os.Stat(filepath.Join(m.Root(), "index-backups")); !os.IsNotExist(e) {
		t.Fatal("load must not write a backup")
	}
	issues := m.IndexRecovery()
	if len(issues.Entries) != 1 || issues.Pending != 1 {
		t.Fatal("missing visible quarantine", issues)
	}
	public, _ := json.Marshal(issues)
	if strings.Contains(string(public), "do-not-return-this") || strings.Contains(string(public), "private_extra") {
		t.Fatal("raw legacy payload leaked")
	}
	if _, e := m.Create("正常新实例", "main", 0, false); e != nil {
		t.Fatal(e)
	}
	issues = m.IndexRecovery()
	backup, e := os.ReadFile(filepath.Join(m.Root(), "index-backups", issues.BackupName))
	if e != nil || string(backup) != string(original) {
		t.Fatal("backup is not exact", e)
	}
	current, _ = os.ReadFile(filepath.Join(m.Root(), "launcher.json"))
	if !strings.Contains(string(current), "do-not-return-this") {
		t.Fatal("private quarantine evidence dropped on save")
	}
	m.Close()
	n, e := New(Config{Root: m.Root()})
	if e != nil {
		t.Fatal(e)
	}
	defer n.Close()
	if len(n.List()) != 2 || n.IndexRecovery().Entries[0].EntryID != issues.Entries[0].EntryID {
		t.Fatal("quarantine not durable")
	}
}

func TestRecoverLegacyCopiesDataKeepsOriginalAndIsIdempotent(t *testing.T) {
	old := legacyRow(t, "weekend-room")
	m, original := indexedManager(t, old)
	source := filepath.Join(m.Root(), "instances", old.ID)
	os.MkdirAll(filepath.Join(source, "data", "assets"), 0700)
	os.WriteFile(filepath.Join(source, "data", "tavern.sqlite3"), []byte("db-fixture"), 0600)
	os.WriteFile(filepath.Join(source, "data", "tavern.sqlite3-wal"), []byte("wal-fixture"), 0600)
	os.WriteFile(filepath.Join(source, "data", "assets", "map.txt"), []byte("map"), 0600)
	os.WriteFile(filepath.Join(source, "python-path"), []byte("do-not-adopt-code"), 0600)
	atomicJSON(filepath.Join(source, "settings.json"), map[string]string{"DECISION_API_KEY": "qa-private-key", "DECISION_MODEL": "qa-model"})
	issue := m.IndexRecovery().Entries[0]
	if !issue.CanRecover {
		t.Fatal("safe legacy folder not recoverable")
	}
	if _, e := m.RecoverIndexEntry(issue.EntryID, false); e == nil {
		t.Fatal("must require stopped confirmation")
	}
	v, e := m.RecoverIndexEntry(issue.EntryID, true)
	if e != nil {
		t.Fatal(e)
	}
	if !validID(v.ID) || v.ID == old.ID || v.Commit != "" || v.RecoveredFromID != old.ID {
		t.Fatal("bad recovered identity", v)
	}
	for file, value := range map[string]string{"tavern.sqlite3": "db-fixture", "tavern.sqlite3-wal": "wal-fixture", "assets/map.txt": "map"} {
		for _, dir := range []string{filepath.Join(source, "data"), v.DataPath} {
			b, e := os.ReadFile(filepath.Join(dir, file))
			if e != nil || string(b) != value {
				t.Fatal("lost original or recovered data", file, e)
			}
		}
	}
	if _, e := os.Stat(filepath.Join(m.path(v.ID), "python-path")); !os.IsNotExist(e) {
		t.Fatal("adopted legacy code")
	}
	settings, e := m.Settings(v.ID)
	if e != nil || settings["DECISION_API_KEY"] != nil || settings["DECISION_API_KEY_configured"] != true {
		t.Fatal("lost settings or echoed key", e)
	}
	again, e := m.RecoverIndexEntry(issue.EntryID, true)
	if e != nil || again.ID != v.ID || len(m.List()) != 1 {
		t.Fatal("retry duplicated recovery", e)
	}
	report := m.IndexRecovery()
	if report.Pending != 0 || report.Entries[0].RestoredID != v.ID {
		t.Fatal("missing recovery result")
	}
	backup, _ := os.ReadFile(filepath.Join(m.Root(), "index-backups", report.BackupName))
	if string(backup) != string(original) {
		t.Fatal("original evidence lost")
	}
	m.Close()
	n, e := New(Config{Root: m.Root()})
	if e != nil {
		t.Fatal(e)
	}
	defer n.Close()
	again, e = n.RecoverIndexEntry(issue.EntryID, true)
	if e != nil || again.ID != v.ID {
		t.Fatal("retry after restart duplicated", e)
	}
}

func TestUnsafeLegacyIDsNeverJoinOrRecover(t *testing.T) {
	for _, value := range []string{"../outside", "/absolute", "a/b", "a\\b", "C:\\secret", ".", "..", "CON", "NUL", "LPT1", strings.Repeat("x", 65)} {
		t.Run(value, func(t *testing.T) {
			m, _ := indexedManager(t, legacyRow(t, value))
			issue := m.IndexRecovery().Entries[0]
			if issue.CanRecover {
				t.Fatal("unsafe directory allowed")
			}
			if _, e := m.RecoverIndexEntry(issue.EntryID, true); e == nil {
				t.Fatal("unsafe recovery accepted")
			}
			if len(m.List()) != 0 {
				t.Fatal("created partial unsafe instance")
			}
		})
	}
}

func TestDuplicateIDsKeepFirstDoNotCopyLiveDirectory(t *testing.T) {
	first := legacyRow(t, strings.Repeat("a", 32))
	second := first
	second.Name = "不得覆盖首条"
	m, _ := indexedManager(t, first, second)
	if len(m.List()) != 1 || m.List()[0].Name != first.Name {
		t.Fatal("duplicate overwrote first row")
	}
	issue := m.IndexRecovery().Entries[0]
	if issue.CanRecover {
		t.Fatal("duplicate live directory offered for copy")
	}
	if _, e := m.RecoverIndexEntry(issue.EntryID, true); e == nil {
		t.Fatal("duplicate recovery allowed")
	}
}
func TestMalformedRowDoesNotHideOtherValidInstances(t *testing.T) {
	m, _ := indexedManager(t, legacyRow(t, strings.Repeat("b", 32)), map[string]any{"id": 123}, legacyRow(t, "port-bad"))
	if len(m.List()) != 1 || len(m.IndexRecovery().Entries) != 2 {
		t.Fatal("invalid row took down whole index")
	}
}
func TestRecoveryRejectsOccupiedPortAndDataSymlink(t *testing.T) {
	old := legacyRow(t, "old-folder")
	m, _ := indexedManager(t, old)
	source := filepath.Join(m.Root(), "instances", old.ID, "data")
	os.MkdirAll(source, 0700)
	issue := m.IndexRecovery().Entries[0]
	listener, e := net.Listen("tcp", fmtPort(old.Port))
	if e != nil {
		t.Fatal(e)
	}
	if _, e = m.RecoverIndexEntry(issue.EntryID, true); e == nil {
		t.Fatal("copied data while old port occupied")
	}
	listener.Close()
	outside := filepath.Join(t.TempDir(), "private.txt")
	os.WriteFile(outside, []byte("must-not-copy"), 0600)
	if e = os.Symlink(outside, filepath.Join(source, "linked.txt")); e != nil {
		t.Skip("symlink unavailable", e)
	}
	if _, e = m.RecoverIndexEntry(issue.EntryID, true); e == nil {
		t.Fatal("followed data link")
	}
	if len(m.List()) != 0 || m.IndexRecovery().Pending != 1 {
		t.Fatal("partial recovery published")
	}
}
func fmtPort(port int) string { return net.JoinHostPort("127.0.0.1", fmt.Sprint(port)) }

func TestUnavailableOrAlteredBackupBlocksIndexWrite(t *testing.T) {
	m, original := indexedManager(t, legacyRow(t, "legacy"))
	os.WriteFile(filepath.Join(m.Root(), "index-backups"), []byte("not-a-dir"), 0600)
	if _, e := m.Create("不能丢档", "main", 0, false); e == nil {
		t.Fatal("saved without backup")
	}
	b, _ := os.ReadFile(filepath.Join(m.Root(), "launcher.json"))
	if string(b) != string(original) || len(m.List()) != 0 {
		t.Fatal("index changed despite backup failure")
	}
	os.Remove(filepath.Join(m.Root(), "index-backups"))
	if _, e := m.Create("安全新实例", "main", 0, false); e != nil {
		t.Fatal(e)
	}
	backup := filepath.Join(m.Root(), "index-backups", m.IndexRecovery().BackupName)
	os.WriteFile(backup, []byte("changed"), 0600)
	before, _ := os.ReadFile(filepath.Join(m.Root(), "launcher.json"))
	if _, e := m.Create("拒绝覆盖", "main", 0, false); e == nil {
		t.Fatal("overwrote with altered evidence")
	}
	after, _ := os.ReadFile(filepath.Join(m.Root(), "launcher.json"))
	if string(before) != string(after) {
		t.Fatal("index changed")
	}
}
func TestUnknownIndexSchemaDoesNotOverwriteAndReleasesLock(t *testing.T) {
	root := t.TempDir()
	path := filepath.Join(root, "launcher.json")
	os.WriteFile(path, []byte(`{"schema":99,"instances":[]}`), 0600)
	if m, e := New(Config{Root: root}); e == nil {
		m.Close()
		t.Fatal("future index accepted")
	}
	os.WriteFile(path, []byte(`{"schema":1,"instances":[]}`), 0600)
	m, e := New(Config{Root: root})
	if e != nil {
		t.Fatal("lock leaked", e)
	}
	m.Close()
}

func TestDuplicateLegacyDirectoriesCannotBeCopiedTwice(t *testing.T) {
	old := legacyRow(t, "same-legacy")
	second := old
	second.Name = "重复旧记录"
	m, _ := indexedManager(t, old, second)
	os.MkdirAll(filepath.Join(m.Root(), "instances", old.ID, "data"), 0700)
	issues := m.IndexRecovery().Entries
	if !issues[0].CanRecover || issues[1].CanRecover {
		t.Fatal("duplicate legacy row should not be offered for recovery", issues)
	}
	if _, e := m.RecoverIndexEntry(issues[0].EntryID, true); e != nil {
		t.Fatal(e)
	}
	if _, e := m.RecoverIndexEntry(issues[1].EntryID, true); e == nil {
		t.Fatal("duplicated source directory adopted")
	}
}
