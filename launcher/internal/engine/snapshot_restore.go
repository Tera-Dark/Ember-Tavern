package engine

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"io"
	"os"
	"path/filepath"
	"time"
)

func (m *Manager) RestoreSnapshot(id, snapshotID, revision, name string) (Task, error) {
	if e := checkName(name); e != nil {
		return Task{}, e
	}
	m.mu.Lock()
	source := m.instances[id]
	if source == nil {
		m.mu.Unlock()
		return Task{}, errors.New("实例不存在")
	}
	if m.processes[id] != nil || m.active[id] != "" {
		m.mu.Unlock()
		return Task{}, errors.New("停止源酒馆并等待任务结束后再恢复")
	}
	old := *source
	m.mu.Unlock()
	report, e := m.Snapshots(id)
	if e != nil {
		return Task{}, e
	}
	if report.Revision != revision {
		return Task{}, errors.New("快照列表已变化，请刷新后选择")
	}
	var chosen Snapshot
	for _, row := range report.Entries {
		if row.ID == snapshotID {
			chosen = row
		}
	}
	if chosen.ID == "" || chosen.Kind != "backup" || chosen.Warning != "" || chosen.InUse {
		return Task{}, errors.New("请选择已知的完整备份；版本快照通过明确版本切换恢复")
	}
	helper := filepath.Join(m.config.BundledSource, "scripts", "launcher_restore_access.py")
	if info, e := os.Lstat(helper); e != nil || !info.Mode().IsRegular() {
		return Task{}, errors.New("此启动器缺少恢复权限保护工具，请使用完整兼容桌面包")
	}
	return m.task(id, "restore", func(t *Task) (err error) {
		// Revalidate after claiming the source task, before creating any destination.
		if e := safeSnapshotPath(m.config.Root, chosen.path); e != nil {
			return e
		}
		if info, e := os.Lstat(chosen.path); e != nil || info.Size() != chosen.Bytes || info.ModTime().UnixNano() != chosen.modified {
			return errors.New("所选备份已变化，请重新预览")
		}
		if e := safeSnapshotPath(m.config.Root, filepath.Join(m.path(id), "data", "tavern.sqlite3")); e != nil {
			return errors.New("源数据库路径无法安全读取，原数据保留")
		}
		m.mu.Lock()
		running := m.processes[id] != nil
		m.mu.Unlock()
		if running {
			return errors.New("源酒馆仍在运行，恢复未开始")
		}
		m.mu.Lock()
		created, e := m.createLocked(name, old.Channel, 0, old.LAN)
		if e != nil {
			m.mu.Unlock()
			return e
		}
		targetID := created.ID
		m.active[targetID] = t.ID
		m.instances[targetID].RecoveredFromID = id
		t.ResultInstanceID = targetID
		e = m.saveLocked()
		m.mu.Unlock()
		defer func() {
			m.mu.Lock()
			delete(m.active, targetID)
			if err != nil {
				m.errors[targetID] = "恢复未完成；源酒馆与原备份保留，请查看恢复任务"
			}
			m.mu.Unlock()
		}()
		if e != nil {
			return e
		}
		root := m.path(targetID)
		work := filepath.Join(root, "work-"+t.ID)
		if e = os.MkdirAll(work, 0700); e != nil {
			return e
		}
		defer os.RemoveAll(work)
		m.progress(t, 10, "复制已安装本体，原酒馆保持停止并保留")
		app := filepath.Join(root, "app")
		if e = copyTree(filepath.Join(m.path(id), "app"), app); e != nil {
			return e
		}
		base, e := m.basePython(t)
		if e != nil {
			return e
		}
		envFolder := filepath.Join(root, "environments", t.ID)
		args := []string{"-m", "venv", envFolder}
		if m.config.SystemPackages {
			args = append(args, "--system-site-packages")
		}
		m.progress(t, 30, "为恢复的酒馆创建独立运行环境")
		if e = m.run(t, 10*time.Minute, "", nil, base, args...); e != nil {
			return e
		}
		python := envPython(envFolder)
		if !m.config.SkipDependencies {
			m.progress(t, 45, "安装恢复本体的锁定依赖")
			if e = m.run(t, 30*time.Minute, app, nil, python, "-m", "pip", "install", "--disable-pip-version-check", "-r", "requirements-lock.txt"); e != nil {
				return e
			}
		}
		if e = os.WriteFile(filepath.Join(root, "python-path"), []byte(python), 0600); e != nil {
			return e
		}
		m.progress(t, 60, "校验完整备份并恢复到新目录")
		file, e := os.Open(chosen.path)
		if e != nil {
			return e
		}
		hash := sha256.New()
		_, e = io.Copy(hash, io.LimitReader(file, 2*1024*1024*1024+1))
		info, statErr := file.Stat()
		file.Close()
		if e != nil || statErr != nil || info.Size() > 2*1024*1024*1024 {
			return errors.New("备份无法校验或超过恢复限制")
		}
		digest := hex.EncodeToString(hash.Sum(nil))
		data := filepath.Join(work, "restored-data")
		if e = m.run(t, 10*time.Minute, app, nil, python, "scripts/restore.py", chosen.path, "--target", data, "--sha256", digest, "--stopped"); e != nil {
			return e
		}
		// Restored Python/capability grants never become execution trust by copying
		// a backup. Exact room pins remain, but the owner must approve them again.
		if e = os.Remove(filepath.Join(data, "plugin-trust.json")); e != nil && !os.IsNotExist(e) {
			return e
		}
		m.progress(t, 75, "预检恢复数据与本体兼容性，社区授权保持关闭")
		if e = m.probe(targetID, t, data); e != nil {
			return e
		}
		m.progress(t, 85, "保留当前房主身份，关闭旧会话与玩家访问待复核")
		if e = m.run(t, 3*time.Minute, app, nil, python, helper, "--source", filepath.Join(m.path(id), "data", "tavern.sqlite3"), "--target", filepath.Join(data, "tavern.sqlite3")); e != nil {
			return e
		}
		if e = m.probe(targetID, t, data); e != nil {
			return e
		}
		// The new managed instance is still stopped; its original empty data is
		// retained, never delete or overwrite an existing player's current progress.
		original := filepath.Join(root, "data")
		if e = os.Rename(original, filepath.Join(work, "empty-data")); e != nil {
			return e
		}
		if e = os.Rename(data, original); e != nil {
			os.Rename(filepath.Join(work, "empty-data"), original)
			return e
		}
		m.mu.Lock()
		next := m.instances[targetID]
		next.Version = old.Version
		next.Commit = old.Commit
		next.VersionTag = old.VersionTag
		next.InstalledAt = timestamp()
		e = m.saveLocked()
		m.mu.Unlock()
		if e != nil {
			return e
		}
		m.progress(t, 100, "恢复的新酒馆已准备，保持停止等待房主审阅与重新邀请")
		return nil
	})
}
