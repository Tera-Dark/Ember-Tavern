package engine

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"
)

func (m *Manager) basePython(t *Task) (string, error) {
	if m.config.Python != "" {
		path, e := exec.LookPath(m.config.Python)
		return path, e
	}
	if runtime.GOOS != "windows" {
		return "", errors.New("自动 Python 部署当前仅支持 Windows x64；开发模式需指定 --dev-python")
	}
	m.runtimeMu.Lock()
	defer m.runtimeMu.Unlock()
	folder := filepath.Join(m.config.Root, "runtimes", "python-"+PythonVersion)
	python := filepath.Join(folder, "python.exe")
	if _, e := os.Stat(python); e == nil {
		return python, nil
	}
	m.progress(t, 12, "下载隔离的 Python 运行环境")
	archive := filepath.Join(m.config.Root, "downloads", "python-"+PythonVersion+"-amd64.zip")
	if e := Download(PythonURL, archive, PythonSHA256, 70<<20, func(got, total int64) {
		if total > 0 {
			m.progress(t, 12+int(got*10/total), "下载 Python 运行环境")
		}
	}); e != nil {
		return "", e
	}
	m.progress(t, 24, "解压便携运行环境（不改注册表 / PATH）")
	stage := folder + ".staging-" + ident()
	defer os.RemoveAll(stage)
	if e := Extract(archive, stage); e != nil {
		return "", e
	}
	for _, file := range []string{"python.exe", "Lib/venv/__init__.py", "Lib/ensurepip/__init__.py"} {
		if _, e := os.Stat(filepath.Join(stage, file)); e != nil {
			return "", errors.New("Python 运行环境不完整")
		}
	}
	if e := os.MkdirAll(filepath.Dir(folder), 0700); e != nil {
		return "", e
	}
	if e := os.Rename(stage, folder); e != nil {
		return "", e
	}
	return python, nil
}
func envPython(folder string) string {
	if runtime.GOOS == "windows" {
		return filepath.Join(folder, "Scripts", "python.exe")
	}
	return filepath.Join(folder, "bin", "python")
}
func (m *Manager) install(t *Task, update bool) (err error) {
	id := t.InstanceID
	m.mu.Lock()
	old := *m.instances[id]
	wasRunning := m.processes[id] != nil
	m.mu.Unlock()
	if update && old.Commit == "" {
		return errors.New("先完成首次安装")
	}
	m.progress(t, 3, "读取 GitHub 版本信息")
	var release Release
	if m.config.LocalSource != "" {
		release = Release{Version: "2.1.0-beta.1", Commit: "local-development", Source: "local"}
	} else {
		release, err = Resolve(old.Channel)
		if err != nil {
			return err
		}
	}
	if update && release.Commit == old.Commit && m.config.LocalSource == "" {
		m.log(t, "已经是当前通道最新版本；未执行重复安装")
		return nil
	}
	base, err := m.basePython(t)
	if err != nil {
		return err
	}
	work := filepath.Join(m.path(id), "work-"+t.ID)
	if err = os.MkdirAll(work, 0700); err != nil {
		return err
	}
	defer os.RemoveAll(work)
	candidate := filepath.Join(work, "app")
	m.progress(t, 30, "拉取 GitHub 项目内容")
	if m.config.LocalSource != "" {
		err = copyTree(m.config.LocalSource, candidate)
	} else {
		archive := filepath.Join(work, "source.zip")
		err = Download(release.URL, archive, "", 120<<20, func(got, total int64) {
			if total > 0 {
				m.progress(t, 30+int(got*12/total), "下载项目源码")
			}
		})
		if err == nil {
			unpacked := filepath.Join(work, "unpacked")
			err = Extract(archive, unpacked)
			if err == nil {
				entries, e := os.ReadDir(unpacked)
				if e != nil || len(entries) != 1 || !entries[0].IsDir() {
					err = errors.New("项目 ZIP 结构无效")
				} else {
					err = os.Rename(filepath.Join(unpacked, entries[0].Name()), candidate)
				}
			}
		}
	}
	if err != nil {
		return err
	}
	for _, name := range []string{"server/app.py", "requirements-lock.txt", "static/index.html"} {
		if _, e := os.Stat(filepath.Join(candidate, name)); e != nil {
			return errors.New("下载内容不是完整余烬项目；缺少 " + name)
		}
	}
	if err = validateDeployment(candidate); err != nil {
		return err
	}
	runtimeFolder := filepath.Join(m.path(id), "environments", t.ID)
	if err = os.MkdirAll(filepath.Dir(runtimeFolder), 0700); err != nil {
		return err
	}
	keepEnv := false
	defer func() {
		if !keepEnv {
			os.RemoveAll(runtimeFolder)
		}
	}()
	m.progress(t, 45, "创建实例专用的依赖环境")
	args := []string{"-m", "venv", runtimeFolder}
	if m.config.SystemPackages {
		args = append(args, "--system-site-packages")
	}
	if err = m.run(t, 10*time.Minute, "", nil, base, args...); err != nil {
		return err
	}
	python := envPython(runtimeFolder)
	if !m.config.SkipDependencies {
		m.progress(t, 52, "自动安装项目依赖")
		if err = m.run(t, 30*time.Minute, candidate, nil, python, "-m", "pip", "install", "--disable-pip-version-check", "-r", "requirements-lock.txt"); err != nil {
			return err
		}
	}
	m.progress(t, 71, "验证新版本与独立环境")
	if err = m.run(t, 2*time.Minute, candidate, nil, python, "-c", "import server.app,uvicorn,httpx; print('应用导入验证通过')"); err != nil {
		return err
	}
	// Database and instance configuration are outside app/, never included in source replacement.
	if wasRunning {
		m.progress(t, 75, "停止当前服务，准备原地更新")
		if err = m.stop(id); err != nil {
			return err
		}
	}
	defer func() {
		if err != nil && wasRunning {
			m.log(t, "保留旧版本，尝试恢复原服务")
			_ = m.start(id, t)
		}
	}()
	if _, e := os.Stat(filepath.Join(m.path(id), "data", "tavern.sqlite3")); e == nil {
		m.progress(t, 78, "备份账号、房间、插件与素材")
		backup := filepath.Join(m.path(id), "backups", "before-"+t.ID+".zip")
		os.MkdirAll(filepath.Dir(backup), 0700)
		// Prefer the existing version's online-backup implementation.
		source := filepath.Join(m.path(id), "app")
		oldPython := m.installedPython(id)
		if _, e := os.Stat(filepath.Join(source, "scripts", "backup.py")); e == nil {
			if err = m.run(t, 8*time.Minute, source, m.childEnv(id), oldPython, "scripts/backup.py", "--bundle", "--output", backup); err != nil {
				return err
			}
		}
	}
	app := filepath.Join(m.path(id), "app")
	previous := filepath.Join(m.path(id), "previous-app")
	oldRuntime := m.installedPython(id)
	if e := os.RemoveAll(previous); e != nil {
		return e
	}
	hadOld := false
	if _, e := os.Stat(app); e == nil {
		hadOld = true
	}
	journal := updateJournal{Prior: old, Python: oldRuntime, HadApp: hadOld}
	journalPath := filepath.Join(m.path(id), "update-journal.json")
	if err = atomicJSON(journalPath, journal); err != nil {
		return err
	}
	if _, e := os.Stat(app); e == nil {
		if e = os.Rename(app, previous); e != nil {
			return fmt.Errorf("旧文件仍被占用，未覆盖：%w", e)
		}
		hadOld = true
	}
	swappedData := false
	originalData := filepath.Join(m.path(id), "data")
	previousData := filepath.Join(m.path(id), "previous-data")
	rollback := func() {
		defer os.Remove(journalPath)
		if swappedData {
			failed := filepath.Join(m.path(id), "failed-data-"+t.ID)
			_ = os.Rename(originalData, failed)
			_ = os.Rename(previousData, originalData)
		}
		os.RemoveAll(app)
		if hadOld {
			os.Rename(previous, app)
		}
		_ = os.WriteFile(filepath.Join(m.path(id), "python-path"), []byte(oldRuntime), 0600)
		m.mu.Lock()
		x := old
		m.instances[id] = &x
		_ = m.saveLocked()
		m.mu.Unlock()
	}
	if err = os.Rename(candidate, app); err != nil {
		rollback()
		return err
	}
	if err = os.WriteFile(filepath.Join(m.path(id), "python-path"), []byte(python), 0600); err != nil {
		rollback()
		return err
	}
	// Test migration against a cloned data directory, before touching the user's real DB.
	m.progress(t, 84, "预检数据库迁移与新服务")
	testData := filepath.Join(work, "test-data")
	if err = copyData(filepath.Join(m.path(id), "data"), testData); err != nil {
		rollback()
		return err
	}
	oldDB := filepath.Join(originalData, "tavern.sqlite3")
	if _, e := os.Stat(oldDB); e == nil {
		snapshotCode := "import sqlite3,sys; src=sqlite3.connect(\"file:\"+sys.argv[1]+\"?mode=ro\",uri=True); dst=sqlite3.connect(sys.argv[2]); src.backup(dst); dst.close(); src.close()"
		os.Remove(filepath.Join(testData, "tavern.sqlite3"))
		if err = m.run(t, 3*time.Minute, app, m.childEnv(id), oldRuntime, "-c", snapshotCode, oldDB, filepath.Join(testData, "tavern.sqlite3")); err != nil {
			rollback()
			return err
		}
	}
	if err = m.probe(id, t, testData); err != nil {
		rollback()
		return fmt.Errorf("新版本预检失败，已回退代码：%w", err)
	}
	if err = os.RemoveAll(previousData); err != nil {
		rollback()
		return err
	}
	journal.DataSwap = true
	if err = atomicJSON(journalPath, journal); err != nil {
		rollback()
		return err
	}
	if err = os.Rename(originalData, previousData); err != nil {
		rollback()
		return err
	}
	if err = os.Rename(testData, originalData); err != nil {
		_ = os.Rename(previousData, originalData)
		rollback()
		return err
	}
	swappedData = true
	m.mu.Lock()
	i := m.instances[id]
	i.Version = release.Version
	i.Commit = release.Commit
	i.UpdatedAt = timestamp()
	if i.InstalledAt == "" {
		i.InstalledAt = timestamp()
	}
	err = m.saveLocked()
	m.mu.Unlock()
	if err != nil {
		rollback()
		return err
	}
	m.progress(t, 94, "安装完成，保留用户数据")
	if wasRunning {
		if err = m.start(id, t); err != nil {
			rollback()
			return fmt.Errorf("新版启动失败，已恢复旧代码：%w", err)
		}
	}
	if err = os.Remove(journalPath); err != nil {
		return err
	}
	keepEnv = true
	m.log(t, "版本已就绪；账号、世界、音频与自装插件仍保存在原实例数据目录")
	return nil
}
func (m *Manager) installedPython(id string) string {
	b, e := os.ReadFile(filepath.Join(m.path(id), "python-path"))
	if e != nil {
		return ""
	}
	return strings.TrimSpace(string(b))
}
func copyData(src, dst string) error {
	return filepath.WalkDir(src, func(path string, d os.DirEntry, e error) error {
		if os.IsNotExist(e) {
			return os.MkdirAll(dst, 0700)
		}
		if e != nil {
			return e
		}
		if d.Type()&os.ModeSymlink != 0 {
			return errors.New("数据目录包含符号链接，请检查")
		}
		rel, _ := filepath.Rel(src, path)
		target := filepath.Join(dst, rel)
		if d.IsDir() {
			return os.MkdirAll(target, 0700)
		}
		if strings.HasSuffix(d.Name(), "-wal") || strings.HasSuffix(d.Name(), "-shm") {
			return nil
		}
		b, e := os.ReadFile(path)
		if e != nil {
			return e
		}
		return os.WriteFile(target, b, 0600)
	})
}
