package engine

import (
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// Explicit opt-in: real venv/subprocess/health/rollback integration, not mocks.
func integrationManager(t *testing.T, source string) *Manager {
	t.Helper()
	python := os.Getenv("EMBER_LAUNCHER_TEST_PYTHON")
	if python == "" {
		t.Skip("set EMBER_LAUNCHER_TEST_PYTHON for subprocess integration")
	}
	if _, e := exec.LookPath(python); e != nil {
		t.Skip("Python unavailable")
	}
	m, e := New(Config{Root: t.TempDir(), Python: python, LocalSource: source, SkipDependencies: true, SystemPackages: true})
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(m.Close)
	return m
}
func waitTask(t *testing.T, m *Manager, task Task, success bool) {
	t.Helper()
	deadline := time.Now().Add(90 * time.Second)
	for time.Now().Before(deadline) {
		rows := m.Tasks()
		for _, row := range rows {
			if row.ID == task.ID && row.Status != "running" {
				if (row.Status == "success") != success {
					t.Fatalf("task %s: %s\n%s", row.Status, row.Error, strings.Join(row.Logs, "\n"))
				}
				return
			}
		}
		time.Sleep(50 * time.Millisecond)
	}
	t.Fatal("integration task timed out")
}
func fixtureApp(t *testing.T) string {
	t.Helper()
	root := t.TempDir()
	os.MkdirAll(filepath.Join(root, "server"), 0700)
	os.MkdirAll(filepath.Join(root, "static"), 0700)
	os.MkdirAll(filepath.Join(root, "scripts"), 0700)
	os.WriteFile(filepath.Join(root, "requirements-lock.txt"), []byte(""), 0600)
	os.WriteFile(filepath.Join(root, "static/index.html"), []byte("ok"), 0600)
	os.WriteFile(filepath.Join(root, "server/__init__.py"), []byte(""), 0600)
	code := `import os,sqlite3
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
BAD_REAL=False
@asynccontextmanager
async def life(app):
 p=Path(os.environ['DATA_DIR']);p.mkdir(parents=True,exist_ok=True)
 db=sqlite3.connect(p/'tavern.sqlite3');db.execute('create table if not exists records (name text)');db.commit()
 if BAD_REAL and p.name=='data':
  db.execute("insert into records values ('failed-new-version')");db.commit();db.close();raise RuntimeError('injected real startup failure')
 db.close();yield
app=FastAPI(lifespan=life)
@app.get('/api/health')
def health():return {'ok':True,'product':'余烬酒馆','version':'fixture'}
@app.get('/records')
def records():
 db=sqlite3.connect(Path(os.environ['DATA_DIR'])/'tavern.sqlite3');r=[x[0] for x in db.execute('select name from records')];db.close();return r
`
	os.WriteFile(filepath.Join(root, "server/app.py"), []byte(code), 0600)
	return root
}
func TestRealInstallUpdateRollbackAndData(t *testing.T) {
	source := fixtureApp(t)
	m := integrationManager(t, source)
	i, e := m.Create("integration", "main", 0, false)
	if e != nil {
		t.Fatal(e)
	}
	task, e := m.Install(i.ID, true)
	if e != nil {
		t.Fatal(e)
	}
	waitTask(t, m, task, true)
	v, _ := m.Get(i.ID)
	if v.Status != "running" {
		t.Fatal("not running")
	}
	py := m.installedPython(i.ID)
	cmd := exec.Command(py, "-c", `import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute("insert into records values ('keep-this-room')");c.commit();c.close()`, filepath.Join(i.DataPath, "tavern.sqlite3"))
	if output, e := cmd.CombinedOutput(); e != nil {
		t.Fatal(e, string(output))
	}
	task, e = m.Update(i.ID)
	if e != nil {
		t.Fatal(e)
	}
	waitTask(t, m, task, true)
	v, _ = m.Get(i.ID)
	if v.Status != "running" {
		t.Fatal("did not restart")
	}
	r, e := http.Get(v.URL + "/records")
	if e != nil {
		t.Fatal(e)
	}
	b, _ := io.ReadAll(r.Body)
	r.Body.Close()
	if !strings.Contains(string(b), "keep-this-room") {
		t.Fatal("lost record")
	}
	path := filepath.Join(source, "server/app.py")
	code, _ := os.ReadFile(path)
	os.WriteFile(path, []byte(strings.Replace(string(code), "BAD_REAL=False", "BAD_REAL=True", 1)), 0600)
	task, e = m.Update(i.ID)
	if e != nil {
		t.Fatal(e)
	}
	waitTask(t, m, task, false)
	v, _ = m.Get(i.ID)
	if v.Status != "running" {
		t.Fatal("old service not recovered", v.Error)
	}
	r, e = http.Get(v.URL + "/records")
	if e != nil {
		t.Fatal(e)
	}
	b, _ = io.ReadAll(r.Body)
	r.Body.Close()
	if !strings.Contains(string(b), "keep-this-room") || strings.Contains(string(b), "failed-new-version") {
		t.Fatal("rollback did not restore original data", string(b))
	}
	if _, e = os.Stat(filepath.Join(m.path(i.ID), "previous-app")); e == nil {
		t.Log("previous version retained")
	}
	task, e = m.Stop(i.ID)
	if e != nil {
		t.Fatal(e)
	}
	waitTask(t, m, task, true)
	v, _ = m.Get(i.ID)
	if v.Status == "running" {
		t.Fatal("did not stop")
	}
}
