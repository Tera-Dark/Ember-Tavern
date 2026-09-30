//go:build windows

package engine

import (
	"fmt"
	"os"
	"os/exec"
	"strings"
	"testing"
)

func TestWindowsPortablePythonBootstrap(t *testing.T) {
	if os.Getenv("EMBER_LAUNCHER_WINDOWS_BOOTSTRAP") != "1" {
		t.Skip("network bootstrap is an explicit Windows CI test")
	}
	m := testManager(t)
	i, _ := m.Create("bootstrap", "main", 0, false)
	task, e := m.task(i.ID, "install", func(task *Task) error {
		python, e := m.basePython(task)
		if e != nil {
			return e
		}
		output, e := exec.Command(python, "-c", "import sys,venv,ensurepip,sqlite3; print(sys.version)").CombinedOutput()
		if e != nil {
			return e
		}
		if !strings.Contains(string(output), PythonVersion) {
			return fmt.Errorf("portable Python version mismatch: %s", output)
		}
		return nil
	})
	if e != nil {
		t.Fatal(e)
	}
	waitTask(t, m, task, true)
}
