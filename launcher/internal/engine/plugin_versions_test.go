package engine

import (
	"os"
	"path/filepath"
	"testing"
)

func TestModuleVersionRPCDoesNotAcceptShellPathsOrUnconfirmedRevisions(t *testing.T) {
	m := testManager(t)
	instance, e := m.Create("modules", "main", 0, false)
	if e != nil {
		t.Fatal(e)
	}
	for _, request := range []ModuleRequest{{Operation: "shell"}, {Operation: "upgrade", Archive: "../source.zip", SHA256: "bad"}, {Operation: "rollback", CheckpointID: "../outside"}} {
		if _, e = m.ModuleVersions(instance.ID, request); e == nil {
			t.Fatal("unsafe module request accepted")
		}
	}
	if len(m.Tasks()) != 0 {
		t.Fatal("rejected requests created tasks")
	}
}
func TestModuleCompatibilityBarrierCannotBeIgnoredWhenRecoveryFilesAreMissing(t *testing.T) {
	root := t.TempDir()
	m, e := New(Config{Root: root})
	if e != nil {
		t.Fatal(e)
	}
	instance, e := m.Create("modules", "main", 0, false)
	if e != nil {
		t.Fatal(e)
	}
	marker := filepath.Join(m.path(instance.ID), "update-journal.json")
	contents := []byte(`{"format":"ember.module-barrier/v1","transaction_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}`)
	if e = os.WriteFile(marker, contents, 0600); e != nil {
		t.Fatal(e)
	}
	m.Close()
	if next, e := New(Config{Root: root}); e == nil {
		next.Close()
		t.Fatal("incomplete module transaction started without recovery files")
	}
	original, e := os.ReadFile(marker)
	if e != nil || string(original) != string(contents) {
		t.Fatal("compatibility marker overwritten", e)
	}
}
