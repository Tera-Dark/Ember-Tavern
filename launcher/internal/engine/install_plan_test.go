package engine

import (
	"net"
	"testing"
)

func TestInstallationPlanUsesRealPortAndPreservesIndex(t *testing.T) {
	m, e := New(Config{Root: t.TempDir()})
	if e != nil {
		t.Fatal(e)
	}
	defer m.Close()
	plan, e := m.InstallationPlan(0)
	if e != nil {
		t.Fatal(e)
	}
	if plan.Port < 8180 || plan.PythonURL != PythonURL || len(m.List()) != 0 {
		t.Fatal("unexpected plan or mutated index")
	}
	listener, e := net.Listen("tcp", fmtPort(plan.Port))
	if e != nil {
		t.Fatal(e)
	}
	defer listener.Close()
	if _, e = m.InstallationPlan(plan.Port); e == nil {
		t.Fatal("occupied port was accepted")
	}
	next, e := m.InstallationPlan(0)
	if e != nil || next.Port == plan.Port {
		t.Fatal("automatic check did not skip occupied port", e)
	}
	if _, e = m.InstallationPlan(80); e == nil {
		t.Fatal("privileged port accepted")
	}
}
