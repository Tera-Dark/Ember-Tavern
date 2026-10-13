package engine

import (
	"archive/zip"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func snapshotFixture(t *testing.T, m *Manager, id, name string, when time.Time) string {
	t.Helper()
	folder := filepath.Join(m.path(id), "backups")
	if e := os.MkdirAll(folder, 0700); e != nil {
		t.Fatal(e)
	}
	path := filepath.Join(folder, name)
	file, e := os.Create(path)
	if e != nil {
		t.Fatal(e)
	}
	archive := zip.NewWriter(file)
	entry, e := archive.Create("backup-manifest.json")
	if e != nil {
		t.Fatal(e)
	}
	entry.Write([]byte(`{"format":"ember-tavern-backup/v2","files":[]}`))
	archive.Close()
	file.Close()
	os.Chtimes(path, when, when)
	return path
}
func TestSnapshotPolicyAndExplicitCleanupProtectCurrentDataAndVersionCheckpoint(t *testing.T) {
	m := testManager(t)
	i, _ := m.Create("snapshots", "main", 0, false)
	now := time.Now()
	oldest := snapshotFixture(t, m, i.ID, "manual-"+strings.Repeat("a", 32)+".zip", now.Add(-2*time.Hour))
	snapshotFixture(t, m, i.ID, "before-"+strings.Repeat("b", 32)+".zip", now.Add(-time.Hour))
	snapshotFixture(t, m, i.ID, "manual-"+strings.Repeat("c", 32)+".zip", now)
	commit := strings.Repeat("d", 40)
	versionPath := filepath.Join(m.path(i.ID), "version-data", commit)
	os.MkdirAll(filepath.Join(versionPath, "data"), 0700)
	atomicJSON(filepath.Join(versionPath, "version.json"), Instance{ID: i.ID, Commit: commit, Version: "2.4.0-beta.1"})
	os.WriteFile(filepath.Join(versionPath, "data", "keep.txt"), []byte("version snapshot"), 0600)
	marker := filepath.Join(m.path(i.ID), "data", "keep.txt")
	os.WriteFile(marker, []byte("current progress"), 0600)
	report, e := m.Snapshots(i.ID)
	if e != nil {
		t.Fatal(e)
	}
	if len(report.Entries) != 4 || report.Bytes <= 0 {
		t.Fatal("inventory missing")
	}
	var old, latest, checkpoint Snapshot
	for _, row := range report.Entries {
		if row.path == oldest {
			old = row
		}
		if row.Name == "manual-"+strings.Repeat("c", 32)+".zip" {
			latest = row
		}
		if row.Kind == "version" {
			checkpoint = row
		}
	}
	if !latest.SystemProtected || latest.CanDelete || !checkpoint.SystemProtected || checkpoint.CanDelete || !old.CanDelete {
		t.Fatal("unsafe protection defaults")
	}
	if e = m.DeleteSnapshots(i.ID, report.Revision, []string{old.ID}, false); e == nil {
		t.Fatal("deleted without explicit confirmation")
	}
	if e = m.DeleteSnapshots(i.ID, report.Revision, []string{latest.ID}, true); e == nil {
		t.Fatal("deleted newest backup")
	}
	if e = m.SetSnapshotPolicy(i.ID, report.Revision, 1, map[string]bool{old.ID: true}); e != nil {
		t.Fatal(e)
	}
	protected, e := m.Snapshots(i.ID)
	if e != nil {
		t.Fatal(e)
	}
	if e = m.DeleteSnapshots(i.ID, report.Revision, []string{old.ID}, true); e == nil {
		t.Fatal("accepted stale revision")
	}
	if e = m.DeleteSnapshots(i.ID, protected.Revision, []string{old.ID}, true); e == nil {
		t.Fatal("deleted user protected snapshot")
	}
	if e = m.SetSnapshotPolicy(i.ID, protected.Revision, 1, map[string]bool{old.ID: false}); e != nil {
		t.Fatal(e)
	}
	ready, _ := m.Snapshots(i.ID)
	if e = m.DeleteSnapshots(i.ID, ready.Revision, []string{old.ID}, true); e != nil {
		t.Fatal(e)
	}
	if _, e = os.Stat(oldest); !os.IsNotExist(e) {
		t.Fatal("history not removed")
	}
	data, _ := os.ReadFile(marker)
	if string(data) != "current progress" {
		t.Fatal("current data touched")
	}
	data, _ = os.ReadFile(filepath.Join(versionPath, "data", "keep.txt"))
	if string(data) != "version snapshot" {
		t.Fatal("version checkpoint touched")
	}
}
func TestSnapshotUnknownPolicyAndBusyStateFailClosed(t *testing.T) {
	m := testManager(t)
	i, _ := m.Create("protected", "main", 0, false)
	snapshotFixture(t, m, i.ID, "manual-"+strings.Repeat("a", 32)+".zip", time.Now())
	m.active[i.ID] = "active-task"
	report, e := m.Snapshots(i.ID)
	if e != nil || !report.Entries[0].InUse || report.Entries[0].CanDelete {
		t.Fatal("busy snapshot not protected", e)
	}
	delete(m.active, i.ID)
	path := filepath.Join(m.path(i.ID), "snapshot-policy.json")
	original := []byte(`{"format":"future/v2","keep_latest":1,"protected":{}}`)
	os.WriteFile(path, original, 0600)
	report, e = m.Snapshots(i.ID)
	if e != nil || !report.ReadOnly || report.Error == "" {
		t.Fatal("future policy was reset", e)
	}
	if e = m.SetSnapshotPolicy(i.ID, report.Revision, 1, map[string]bool{}); e == nil {
		t.Fatal("overwrote unknown policy")
	}
	after, _ := os.ReadFile(path)
	if string(after) != string(original) {
		t.Fatal("future original changed")
	}
}
func TestSnapshotCleanupRejectsExternalLinkAndArbitraryIdentifiers(t *testing.T) {
	m := testManager(t)
	i, _ := m.Create("scope", "main", 0, false)
	outside := t.TempDir()
	keep := filepath.Join(outside, "keep.txt")
	os.WriteFile(keep, []byte("outside must survive"), 0600)
	if e := safeSnapshotPath(m.config.Root, outside); e == nil {
		t.Fatal("accepted a target outside root")
	}
	report, _ := m.Snapshots(i.ID)
	if e := m.DeleteSnapshots(i.ID, report.Revision, []string{"../data"}, true); e == nil {
		t.Fatal("accepted a caller path")
	}
	versionPath := filepath.Join(m.path(i.ID), "version-data", strings.Repeat("f", 40))
	os.MkdirAll(filepath.Dir(versionPath), 0700)
	if e := os.Symlink(outside, versionPath); e != nil {
		t.Log("symlink creation unavailable; ordinary boundary checks passed")
		return
	}
	report, e := m.Snapshots(i.ID)
	if e != nil {
		t.Fatal(e)
	}
	if report.Entries[0].CanDelete || report.Entries[0].Warning == "" {
		t.Fatal("unsafe link eligible")
	}
	data, _ := os.ReadFile(keep)
	if string(data) != "outside must survive" {
		t.Fatal("external target touched")
	}
}
func TestSnapshotRevisionTracksSubsecondReplacement(t *testing.T) {
	m := testManager(t)
	i, _ := m.Create("revision", "main", 0, false)
	now := time.Now().Truncate(time.Second)
	path := snapshotFixture(t, m, i.ID, "manual-"+strings.Repeat("e", 32)+".zip", now)
	before, _ := m.Snapshots(i.ID)
	os.Chtimes(path, now.Add(time.Millisecond), now.Add(time.Millisecond))
	after, _ := m.Snapshots(i.ID)
	if before.Revision == after.Revision {
		t.Fatal("subsecond change invisible")
	}
	body, _ := json.Marshal(after)
	if strings.Contains(string(body), m.Root()) {
		t.Fatal("inventory exposes filesystem path")
	}
}
