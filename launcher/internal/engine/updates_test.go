package engine

import (
	"archive/zip"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

type updateTransport func(*http.Request) (*http.Response, error)

func (f updateTransport) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }
func mockGitHub(t *testing.T, fn func(*http.Request) (string, int)) {
	t.Helper()
	original := HTTPClient
	HTTPClient = &http.Client{Transport: updateTransport(func(r *http.Request) (*http.Response, error) {
		body, status := fn(r)
		return &http.Response{StatusCode: status, Header: make(http.Header), Body: io.NopCloser(strings.NewReader(body)), Request: r}, nil
	})}
	t.Cleanup(func() { HTTPClient = original })
}
func TestReleaseCatalogIncludesBetaAndPagination(t *testing.T) {
	pages := 0
	mockGitHub(t, func(r *http.Request) (string, int) {
		pages++
		if r.URL.Query().Get("page") == "1" {
			rows := make([]map[string]any, 100)
			for i := range rows {
				rows[i] = map[string]any{"tag_name": fmt.Sprintf("plugin-note-%d", i)}
			}
			b, _ := json.Marshal(rows)
			return string(b), 200
		}
		return `[{"tag_name":"desktop-v0.2.0-beta.9"},{"tag_name":"desktop-v0.2.0-beta.10"},{"tag_name":"v2.4.0"},{"tag_name":"desktop-v9.0.0","draft":true},{"tag_name":"desktop-v1.0.0-beta.01"}]`, 200
	})
	rows, e := ReleaseTags()
	if e != nil || len(rows) != 3 || rows[0].Tag != "desktop-v0.2.0-beta.10" || pages != 2 {
		t.Fatal(rows, e, pages)
	}
}
func TestBundledCheckQueriesGitHubAndPersistsRollbackSuppression(t *testing.T) {
	latest := strings.Repeat("b", 40)
	mockGitHub(t, func(r *http.Request) (string, int) {
		switch {
		case strings.Contains(r.URL.Path, "/releases/tags/"):
			return `{"tag_name":"desktop-v0.2.0-beta.5"}`, 200
		case strings.HasSuffix(r.URL.Path, "/releases"):
			return `[{"tag_name":"desktop-v0.2.0-beta.5"}]`, 200
		case strings.Contains(r.URL.Path, "/commits/"):
			return `{"sha":"` + latest + `"}`, 200
		case strings.HasSuffix(r.URL.Path, "launcher-manifest.json"):
			return `{"format":"ember-deploy/v1","app_version":"2.4.0-beta.2"}`, 200
		default:
			t.Errorf("unexpected request %s", r.URL)
			return "", 404
		}
	})
	m := testManager(t)
	m.config.BundledSource = t.TempDir()
	v, e := m.Create("old bundled", "bundled", 0, false)
	if e != nil {
		t.Fatal(e)
	}
	m.mu.Lock()
	m.instances[v.ID].Commit = strings.Repeat("a", 40)
	m.instances[v.ID].Version = "2.4.0-beta.1"
	m.mu.Unlock()
	if _, e = m.Check(v.ID); e != nil {
		t.Fatal(e)
	}
	row, _ := m.Get(v.ID)
	if !row.Update.Available {
		t.Fatal(row.Update)
	}
	m.mu.Lock()
	m.instances[v.ID].IgnoredUpdate = latest
	if e = m.saveLocked(); e != nil {
		t.Fatal(e)
	}
	m.mu.Unlock()
	root := m.Root()
	m.Close()
	n, e := New(Config{Root: root})
	if e != nil {
		t.Fatal(e)
	}
	defer n.Close()
	n.Check(v.ID)
	row, _ = n.Get(v.ID)
	if row.Update.Available || !row.Update.Suppressed {
		t.Fatal(row.Update)
	}
	latest = strings.Repeat("c", 40)
	n.remoteCache = nil
	n.Check(v.ID)
	row, _ = n.Get(v.ID)
	if !row.Update.Available || row.Update.Suppressed {
		t.Fatal(row.Update)
	}
}
func TestResolveOnlyPublishedValidTagsAndExactHexCommit(t *testing.T) {
	for _, tag := range []string{"../main", "plugin-v1.0.0", "desktop-v1.0", "v1.0.0/evil"} {
		if _, e := ResolveTag(tag); e == nil {
			t.Fatal(tag)
		}
	}
	mockGitHub(t, func(r *http.Request) (string, int) {
		if strings.Contains(r.URL.Path, "releases/tags") {
			return `{"tag_name":"desktop-v1.0.0"}`, 200
		}
		return `{"sha":"` + strings.Repeat("z", 40) + `"}`, 200
	})
	if _, e := ResolveTag("desktop-v1.0.0"); e == nil {
		t.Fatal("nonhex commit accepted")
	}
}
func TestFailedCheckRetainsInstalledVersionAndReportsNetworkError(t *testing.T) {
	mockGitHub(t, func(r *http.Request) (string, int) { return "rate limited", 403 })
	m := testManager(t)
	i, _ := m.Create("offline", "release", 0, false)
	m.mu.Lock()
	m.instances[i.ID].Version = "1.0.0"
	m.instances[i.ID].Commit = strings.Repeat("a", 40)
	m.mu.Unlock()
	if _, e := m.Check(i.ID); e == nil {
		t.Fatal("check should fail")
	}
	v, _ := m.Get(i.ID)
	if v.Update.Error == "" || v.Update.Available || v.Version != "1.0.0" {
		t.Fatal(v)
	}
}
func TestInstancesShareSuccessfulAndFailedChecks(t *testing.T) {
	calls := 0
	mockGitHub(t, func(r *http.Request) (string, int) { calls++; return "limited", 403 })
	m := testManager(t)
	a, _ := m.Create("one", "release", 0, false)
	b, _ := m.Create("two", "release", 0, false)
	m.Check(a.ID)
	m.Check(b.ID)
	if calls != 1 {
		t.Fatal("failed checks exhausted quota", calls)
	}
}
func sourceArchive(t *testing.T, source string) string {
	t.Helper()
	var data bytes.Buffer
	w := zip.NewWriter(&data)
	e := filepath.WalkDir(source, func(path string, d os.DirEntry, e error) error {
		if e != nil {
			return e
		}
		if d.IsDir() {
			return nil
		}
		name, _ := filepath.Rel(source, path)
		f, e := w.Create("fixture/" + filepath.ToSlash(name))
		if e != nil {
			return e
		}
		b, e := os.ReadFile(path)
		if e != nil {
			return e
		}
		_, e = f.Write(b)
		return e
	})
	if e != nil {
		t.Fatal(e)
	}
	if e = w.Close(); e != nil {
		t.Fatal(e)
	}
	return data.String()
}
func TestRealVersionSwitchRestoresCheckpointAndDismissesLatest(t *testing.T) {
	source := fixtureApp(t)
	m := integrationManager(t, source)
	a, b := strings.Repeat("a", 40), strings.Repeat("b", 40)
	m.config.BundledCommit = a
	i, e := m.Create("version switch", "main", 0, false)
	if e != nil {
		t.Fatal(e)
	}
	task, e := m.Install(i.ID, true)
	if e != nil {
		t.Fatal(e)
	}
	waitTask(t, m, task, true)
	m.mu.Lock()
	m.instances[i.ID].Version = "1.0.0"
	m.instances[i.ID].VersionTag = "desktop-v1.0.0"
	m.mu.Unlock()
	db := filepath.Join(i.DataPath, "tavern.sqlite3")
	insert := func(value string) {
		t.Helper()
		out, e := exec.Command(m.installedPython(i.ID), "-c", "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]);c.execute('insert into records values (?)',(sys.argv[2],));c.commit();c.close()", db, value).CombinedOutput()
		if e != nil {
			t.Fatal(e, string(out))
		}
	}
	insert("old-progress")
	archive := sourceArchive(t, source)
	mockGitHub(t, func(r *http.Request) (string, int) { return archive, 200 })
	newest := Release{Version: "2.0.0", Tag: "desktop-v2.0.0", Commit: b, Source: "release", URL: "https://codeload.github.com/" + Repository + "/zip/" + b}
	m.updates[i.ID] = &UpdateStatus{Latest: &newest, Available: true}
	task, e = m.task(i.ID, "switch", func(task *Task) error { return m.installRelease(task, true, &newest) })
	if e != nil {
		t.Fatal(e)
	}
	waitTask(t, m, task, true)
	insert("new-progress")
	previous := Release{Version: "1.0.0", Tag: "desktop-v1.0.0", Commit: a, Source: "release", URL: "https://codeload.github.com/" + Repository + "/zip/" + a}
	task, e = m.task(i.ID, "switch", func(task *Task) error { return m.installRelease(task, true, &previous) })
	if e != nil {
		t.Fatal(e)
	}
	waitTask(t, m, task, true)
	v, _ := m.Get(i.ID)
	if v.Version != "1.0.0" || v.Status != "running" || v.IgnoredUpdate != b || v.Update.Available || !v.Update.Suppressed {
		t.Fatal(v)
	}
	out, e := exec.Command(m.installedPython(i.ID), "-c", "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]);print([x[0] for x in c.execute('select name from records')]);c.close()", db).CombinedOutput()
	if e != nil || !strings.Contains(string(out), "old-progress") || strings.Contains(string(out), "new-progress") {
		t.Fatal(string(out), e)
	}
	out, e = exec.Command(m.installedPython(i.ID), "-c", "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]);print([x[0] for x in c.execute('select name from records')]);c.close()", filepath.Join(m.path(i.ID), "version-data", b, "data", "tavern.sqlite3")).CombinedOutput()
	if e != nil || !strings.Contains(string(out), "new-progress") {
		t.Fatal("new progress lost", string(out), e)
	}
}
