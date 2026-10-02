package engine

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
)

func validateDeployment(folder string) error {
	b, e := os.ReadFile(filepath.Join(folder, "launcher-manifest.json"))
	if os.IsNotExist(e) {
		return nil
	}
	if e != nil {
		return e
	}
	var m struct {
		Format       string `json:"format"`
		Python       string `json:"python_series"`
		Minimum      string `json:"minimum_launcher"`
		Requirements string `json:"requirements_file"`
		Entrypoint   string `json:"entrypoint"`
		Health       string `json:"health_path"`
	}
	if e = json.Unmarshal(b, &m); e != nil {
		return errors.New("部署清单格式错误")
	}
	if m.Format != "ember-deploy/v1" || m.Python != "3.13" || m.Requirements != "requirements-lock.txt" || m.Entrypoint != "server.app:app" || m.Health != "/api/health" {
		return errors.New("新版本的部署协议 / Python 已变化，请先更新启动器，旧版本保持不变")
	}
	supported, e := versionAtLeast(LauncherVersion, m.Minimum)
	if e != nil {
		return errors.New("最低启动器版本无效")
	}
	if !supported {
		return errors.New("此项目版本需要更新的启动器，未执行安装")
	}
	return nil
}
