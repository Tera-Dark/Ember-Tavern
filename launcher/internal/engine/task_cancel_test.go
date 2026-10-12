package engine

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"sync/atomic"
	"testing"
	"time"
)

func waitTerminalTask(t *testing.T, m *Manager, id string) Task {
	t.Helper()
	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		for _, row := range m.Tasks() {
			if row.ID == id && row.Status != "running" {
				return row
			}
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatal("task did not finish")
	return Task{}
}
func TestForeignHealthCannotBlessUnboundCandidate(t *testing.T) {
	var calls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"ok":true,"product":"余烬酒馆"}`))
	}))
	defer server.Close()
	address, _ := url.Parse(server.URL)
	port, _ := strconv.Atoi(address.Port())
	candidate := &runtimeProcess{done: make(chan struct{}), bound: make(chan struct{})}
	if e := waitRuntimeHealth(port, candidate, 30*time.Millisecond); e == nil {
		t.Fatal("accepted another service as our candidate")
	}
	if calls.Load() != 0 {
		t.Fatal("contacted another instance before own bind")
	}
}

func TestCloseRetainsRootLockUntilTaskCleanupFinishes(t *testing.T) {
	m := testManager(t)
	i, _ := m.Create("shutdown", "main", 0, false)
	entered, cleanup, finished := make(chan struct{}), make(chan struct{}), make(chan struct{})
	_, e := m.task(i.ID, "install", func(task *Task) error {
		close(entered)
		<-task.ctx.Done()
		close(cleanup)
		<-finished
		return task.ctx.Err()
	})
	if e != nil {
		t.Fatal(e)
	}
	<-entered
	closed := make(chan struct{})
	go func() { m.Close(); close(closed) }()
	<-cleanup
	premature, e := New(Config{Root: m.Root()})
	if e == nil {
		premature.Close()
		close(finished)
		t.Fatal("root lock released before cleanup")
	}
	close(finished)
	select {
	case <-closed:
	case <-time.After(3 * time.Second):
		t.Fatal("shutdown did not complete")
	}
	restored, e := New(Config{Root: m.Root()})
	if e != nil {
		t.Fatal(e)
	}
	restored.Close()
}
func TestCancellationWinsBeforeCommitAndNeverAffectsAnotherInstance(t *testing.T) {
	m := testManager(t)
	a, _ := m.Create("first", "main", 0, false)
	b, _ := m.Create("second", "main", 0, false)
	entered := make(chan struct{})
	job, e := m.task(a.ID, "install", func(task *Task) error { close(entered); <-task.ctx.Done(); return m.beginCommit(task) })
	if e != nil {
		t.Fatal(e)
	}
	<-entered
	other, e := m.task(b.ID, "stop", func(task *Task) error { return nil })
	if e != nil {
		t.Fatal(e)
	}
	if e = m.CancelTask(job.ID); e != nil {
		t.Fatal(e)
	}
	result := waitTerminalTask(t, m, job.ID)
	if result.Status != "cancelled" || result.Cancellable || !result.Retryable {
		t.Fatal("invalid cancellation state", result)
	}
	if waitTerminalTask(t, m, other.ID).Status != "success" {
		t.Fatal("other instance affected")
	}
	if view, _ := m.Get(a.ID); view.Error != "" {
		t.Fatal("cancellation became an instance failure")
	}
	if e = m.CancelTask(job.ID); e == nil {
		t.Fatal("cancelled terminal task")
	}
}
func TestCommitBoundaryRejectsCancellation(t *testing.T) {
	m := testManager(t)
	i, _ := m.Create("commit", "main", 0, false)
	entered, finish := make(chan struct{}), make(chan struct{})
	defer func() {
		select {
		case <-finish:
		default:
			close(finish)
		}
	}()
	job, e := m.task(i.ID, "update", func(task *Task) error {
		if e := m.beginCommit(task); e != nil {
			return e
		}
		close(entered)
		<-finish
		return nil
	})
	if e != nil {
		t.Fatal(e)
	}
	<-entered
	if e = m.CancelTask(job.ID); e == nil {
		t.Fatal("cancelled a critical transaction")
	}
	close(finish)
	if waitTerminalTask(t, m, job.ID).Status != "success" {
		t.Fatal("commit failed")
	}
}
func TestDownloadCancellationClosesStreamAndDiscardsPartialFile(t *testing.T) {
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("chunk"))
		w.(http.Flusher).Flush()
		<-r.Context().Done()
	}))
	defer server.Close()
	original := HTTPClient
	HTTPClient = server.Client()
	defer func() { HTTPClient = original }()
	ctx, cancel := context.WithCancel(context.Background())
	path := filepath.Join(t.TempDir(), "download.zip")
	e := DownloadContext(ctx, server.URL, path, "", 1024, func(got, total int64) { cancel() })
	if !errors.Is(e, context.Canceled) {
		t.Fatal("download did not cancel", e)
	}
	if _, e = os.Stat(path); !os.IsNotExist(e) {
		t.Fatal("published incomplete download")
	}
	if _, e = os.Stat(path + ".part"); !os.IsNotExist(e) {
		t.Fatal("left partial download")
	}
}
func TestTaskHistoryRestoresFailureAndPreservesFutureOriginal(t *testing.T) {
	m := testManager(t)
	i, _ := m.Create("history", "main", 0, false)
	job, e := m.task(i.ID, "start", func(task *Task) error { return errors.New("synthetic failure") })
	if e != nil {
		t.Fatal(e)
	}
	waitTerminalTask(t, m, job.ID)
	m.Close()
	restored, e := New(Config{Root: m.Root()})
	if e != nil {
		t.Fatal(e)
	}
	rows := restored.Tasks()
	if len(rows) != 1 || rows[0].ID != job.ID || rows[0].Status != "failed" || !rows[0].Retryable {
		t.Fatal("failure disappeared", rows)
	}
	retry, e := restored.RetryTask(job.ID)
	if e != nil || retry.InstanceID != i.ID || retry.Kind != "start" {
		t.Fatal("retry changed target", e)
	}
	waitTerminalTask(t, restored, retry.ID)
	restored.Close()
	path := filepath.Join(m.Root(), "task-history.json")
	original := []byte(`{"format":"future/v2","tasks":[]}`)
	if e = os.WriteFile(path, original, 0600); e != nil {
		t.Fatal(e)
	}
	future, e := New(Config{Root: m.Root()})
	if e != nil {
		t.Fatal(e)
	}
	defer future.Close()
	if future.TaskHistoryError() == "" {
		t.Fatal("future history silently reset")
	}
	later, e := future.Stop(i.ID)
	if e != nil {
		t.Fatal(e)
	}
	waitTerminalTask(t, future, later.ID)
	after, _ := os.ReadFile(path)
	if string(after) != string(original) {
		t.Fatal("overwrote future history")
	}
}
