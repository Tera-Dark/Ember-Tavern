package engine

import "errors"

type InstallationPlan struct {
	Port          int    `json:"port"`
	PythonURL     string `json:"python_url"`
	PythonVersion string `json:"python_version"`
	DependencyURL string `json:"dependency_url"`
}

// This is a check, not a reservation. Create and start retain their own guards.
func (m *Manager) InstallationPlan(port int) (InstallationPlan, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.closing {
		return InstallationPlan{}, errors.New("启动器正在退出")
	}
	if len(m.instances) >= 24 {
		return InstallationPlan{}, errors.New("最多管理 24 个实例")
	}
	automatic := port == 0
	if automatic {
		port = 8180
	}
	for ; port <= 65535; port++ {
		if port < 1024 {
			return InstallationPlan{}, errors.New("端口需在 1024–65535")
		}
		used := false
		for _, instance := range m.instances {
			if instance.Port == port {
				used = true
				break
			}
		}
		if used {
			if automatic {
				continue
			}
			return InstallationPlan{}, errors.New("该端口已分配给另一个实例")
		}
		if e := availablePort(port); e != nil {
			if automatic {
				continue
			}
			return InstallationPlan{}, e
		}
		return InstallationPlan{Port: port, PythonURL: PythonURL, PythonVersion: PythonVersion, DependencyURL: "https://pypi.org/simple/fastapi/"}, nil
	}
	return InstallationPlan{}, errors.New("没有可用端口，请检查本机服务")
}
