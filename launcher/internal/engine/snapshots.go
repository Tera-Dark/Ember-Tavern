package engine

import (
	"archive/zip"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"
)

type Snapshot struct {
	ID              string `json:"id"`
	Kind            string `json:"kind"`
	Name            string `json:"name"`
	Version         string `json:"version,omitempty"`
	Commit          string `json:"commit,omitempty"`
	CreatedAt       string `json:"created_at"`
	Bytes           int64  `json:"bytes"`
	Protected       bool   `json:"protected"`
	SystemProtected bool   `json:"system_protected"`
	InUse           bool   `json:"in_use"`
	CanDelete       bool   `json:"can_delete"`
	Candidate       bool   `json:"candidate"`
	Warning         string `json:"warning,omitempty"`
	path            string
	modified        int64
}
type SnapshotReport struct {
	Entries    []Snapshot `json:"entries"`
	Bytes      int64      `json:"bytes"`
	KeepLatest int        `json:"keep_latest"`
	Revision   string     `json:"revision"`
	ReadOnly   bool       `json:"read_only"`
	Error      string     `json:"error,omitempty"`
}
type snapshotPolicy struct {
	Format     string          `json:"format"`
	KeepLatest int             `json:"keep_latest"`
	Protected  map[string]bool `json:"protected"`
}

var generatedBackupName = regexp.MustCompile(`^(?:before|manual)-[a-f0-9]{32}\.zip$`)
var checkpointName = regexp.MustCompile(`^[a-f0-9]{40}(?:\.previous-[a-f0-9]{32})?$`)

func snapshotID(instance, kind, name string) string {
	sum := sha256.Sum256([]byte(instance + "/" + kind + "/" + name))
	return hex.EncodeToString(sum[:16])
}
func (m *Manager) snapshotPolicy(id string) (snapshotPolicy, error) {
	result := snapshotPolicy{Format: "ember.snapshot-policy/v1", KeepLatest: 10, Protected: map[string]bool{}}
	path := filepath.Join(m.path(id), "snapshot-policy.json")
	info, e := os.Lstat(path)
	if os.IsNotExist(e) {
		return result, nil
	}
	if e != nil || !info.Mode().IsRegular() || info.Size() > 128<<10 {
		return result, errors.New("快照保护策略无法读取，原文件保留；本次不能修改或清理")
	}
	b, e := os.ReadFile(path)
	if e != nil {
		return result, e
	}
	if e = json.Unmarshal(b, &result); e != nil || result.Format != "ember.snapshot-policy/v1" || result.KeepLatest < 1 || result.KeepLatest > 100 || result.Protected == nil || len(result.Protected) > 1000 {
		return result, errors.New("快照策略格式未知或损坏，原文件保留；本次不能修改或清理")
	}
	for id := range result.Protected {
		if !validID(id) {
			return result, errors.New("快照策略标识无效，原文件保留")
		}
	}
	return result, nil
}
func safeSnapshotPath(base, path string) error {
	base, _ = filepath.Abs(base)
	path, _ = filepath.Abs(path)
	rel, e := filepath.Rel(base, path)
	if e != nil || rel == "." || rel == ".." || filepath.IsAbs(rel) || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return errors.New("快照路径不在实例范围内")
	}
	current := base
	for _, part := range append([]string{""}, strings.Split(rel, string(filepath.Separator))...) {
		if part != "" {
			current = filepath.Join(current, part)
		}
		info, e := os.Lstat(current)
		if e != nil {
			return e
		}
		if info.Mode()&os.ModeSymlink != 0 || !info.IsDir() && !info.Mode().IsRegular() {
			return errors.New("快照路径包含链接或特殊文件，请先检查")
		}
	}
	return nil
}
func treeBytes(path string) (int64, error) {
	var bytes int64
	count := 0
	e := filepath.WalkDir(path, func(path string, entry fs.DirEntry, e error) error {
		if e != nil {
			return e
		}
		count++
		if count > 20000 {
			return errors.New("快照文件过多，暂不统计或清理")
		}
		info, e := entry.Info()
		if e != nil {
			return e
		}
		if info.Mode()&os.ModeSymlink != 0 || !info.IsDir() && !info.Mode().IsRegular() {
			return errors.New("快照包含链接或特殊文件")
		}
		if !info.IsDir() {
			bytes += info.Size()
		}
		return nil
	})
	return bytes, e
}
func backupMetadata(path string) bool {
	archive, e := zip.OpenReader(path)
	if e != nil {
		return false
	}
	defer archive.Close()
	if len(archive.File) > 10000 {
		return false
	}
	for _, file := range archive.File {
		if file.Name == "backup-manifest.json" {
			if file.UncompressedSize64 > 128<<10 {
				return false
			}
			reader, e := file.Open()
			if e != nil {
				return false
			}
			defer reader.Close()
			var value struct {
				Format string `json:"format"`
			}
			if json.NewDecoder(reader).Decode(&value) != nil {
				return false
			}
			return value.Format == "ember-tavern-backup/v2"
		}
	}
	return false
}
func (m *Manager) scanSnapshots(id string, running, busy bool) (SnapshotReport, snapshotPolicy, error) {
	if e := safeSnapshotPath(m.config.Root, m.path(id)); e != nil {
		return SnapshotReport{}, snapshotPolicy{}, errors.New("实例快照目录无法安全读取，原数据保留")
	}
	policy, e := m.snapshotPolicy(id)
	report := SnapshotReport{Entries: []Snapshot{}, KeepLatest: policy.KeepLatest}
	if e != nil {
		report.ReadOnly = true
		report.Error = e.Error()
		policy = snapshotPolicy{Format: "ember.snapshot-policy/v1", KeepLatest: 10, Protected: map[string]bool{}}
		report.KeepLatest = 10
	}
	for _, kind := range []string{"backup", "version"} {
		folder := "backups"
		if kind == "version" {
			folder = "version-data"
		}
		base := filepath.Join(m.path(id), folder)
		info, e := os.Lstat(base)
		if os.IsNotExist(e) {
			continue
		}
		if e != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
			return report, policy, errors.New("快照目录无法读取或包含链接；原目录保留")
		}
		files, e := os.ReadDir(base)
		if e != nil {
			return report, policy, e
		}
		if len(files) > 1000 {
			return report, policy, errors.New("快照目录项目过多，请先保留原目录并检查")
		}
		for _, file := range files {
			if kind == "backup" && !generatedBackupName.MatchString(file.Name()) || kind == "version" && !checkpointName.MatchString(file.Name()) {
				continue
			}
			path := filepath.Join(base, file.Name())
			info, e := os.Lstat(path)
			if e != nil {
				return report, policy, e
			}
			row := Snapshot{ID: snapshotID(id, kind, file.Name()), Kind: kind, Name: file.Name(), CreatedAt: info.ModTime().UTC().Format(time.RFC3339), InUse: busy, path: path, modified: info.ModTime().UnixNano()}
			if e = safeSnapshotPath(m.config.Root, path); e != nil {
				row.Warning = "目录包含链接或特殊文件，保留并检查"
			} else if kind == "backup" {
				row.Bytes = info.Size()
				if !info.Mode().IsRegular() || !backupMetadata(path) {
					row.Warning = "备份格式需要检查；不会清理未知包"
				}
			} else {
				row.Commit = file.Name()[:40]
				var version Instance
				metadata := filepath.Join(path, "version.json")
				var b []byte
				metaInfo, e := os.Lstat(metadata)
				if e == nil && metaInfo.Mode().IsRegular() && metaInfo.Size() <= 32768 {
					b, e = os.ReadFile(metadata)
				} else {
					e = errors.New("invalid snapshot metadata")
				}
				if e != nil || len(b) > 32768 || json.Unmarshal(b, &version) != nil || version.ID != id || version.Commit != row.Commit {
					row.Warning = "版本信息不完整；原快照保留"
				} else {
					row.Version = version.Version
				}
				if size, e := treeBytes(path); e != nil {
					row.Warning = "快照无法完整统计，可能含链接；保留并检查"
				} else {
					row.Bytes = size
				}
			}
			report.Bytes += row.Bytes
			report.Entries = append(report.Entries, row)
		}
	}
	sort.Slice(report.Entries, func(i, j int) bool {
		if report.Entries[i].modified == report.Entries[j].modified {
			return report.Entries[i].ID > report.Entries[j].ID
		}
		return report.Entries[i].modified > report.Entries[j].modified
	})
	versions := map[string]int{}
	latestBackup := -1
	for i, row := range report.Entries {
		if row.Kind == "backup" {
			if latestBackup < 0 {
				latestBackup = i
			}
		} else {
			_, ok := versions[row.Commit]
			if !ok || row.Name == row.Commit {
				versions[row.Commit] = i
			}
		}
	}
	for i := range report.Entries {
		row := &report.Entries[i]
		row.SystemProtected = row.Kind == "backup" && i == latestBackup || row.Kind == "version" && versions[row.Commit] == i
		row.Protected = row.SystemProtected || policy.Protected[row.ID] || report.ReadOnly
		row.CanDelete = !running && !busy && !row.Protected && row.Warning == ""
		row.Candidate = row.CanDelete && i >= policy.KeepLatest
	}
	stamps := []int64{}
	for _, row := range report.Entries {
		stamps = append(stamps, row.modified)
	}
	data, _ := json.Marshal(struct {
		Entries       []Snapshot
		Policy        snapshotPolicy
		Busy, Running bool
		Stamps        []int64
	}{report.Entries, policy, busy, running, stamps})
	sum := sha256.Sum256(data)
	report.Revision = hex.EncodeToString(sum[:])
	return report, policy, nil
}
func (m *Manager) Snapshots(id string) (SnapshotReport, error) {
	m.mu.Lock()
	exists := m.instances[id] != nil
	running, busy := m.processes[id] != nil, m.active[id] != ""
	m.mu.Unlock()
	if !exists {
		return SnapshotReport{}, errors.New("实例不存在")
	}
	report, _, e := m.scanSnapshots(id, running, busy)
	return report, e
}
func (m *Manager) SetSnapshotPolicy(id, revision string, keep int, protected map[string]bool) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.instances[id] == nil {
		return errors.New("实例不存在")
	}
	if m.active[id] != "" {
		return errors.New("等待实例任务结束后再修改快照策略")
	}
	report, policy, e := m.scanSnapshots(id, m.processes[id] != nil, false)
	if e != nil {
		return e
	}
	if report.ReadOnly {
		return errors.New(report.Error)
	}
	if revision != report.Revision {
		return errors.New("快照列表发生变化，请刷新后重新选择")
	}
	if keep < 1 || keep > 100 || len(protected) > 1000 {
		return errors.New("快照策略超出范围")
	}
	for key, value := range protected {
		found := false
		for _, row := range report.Entries {
			if row.ID == key {
				found = true
				if row.SystemProtected && !value {
					return errors.New("最新备份与各版本当前快照必须保留")
				}
			}
		}
		if !found {
			return errors.New("请选择当前列表中的快照")
		}
		policy.Protected[key] = value
	}
	present := map[string]bool{}
	for _, row := range report.Entries {
		present[row.ID] = true
	}
	for key := range policy.Protected {
		if !present[key] {
			delete(policy.Protected, key)
		}
	}
	if len(policy.Protected) > 1000 {
		return errors.New("快照保护数量超过范围")
	}
	policy.KeepLatest = keep
	return atomicJSON(filepath.Join(m.path(id), "snapshot-policy.json"), policy)
}
func (m *Manager) DeleteSnapshots(id, revision string, ids []string, confirm bool) error {
	if !confirm {
		return errors.New("需要明确确认永久删除所选历史快照")
	}
	if len(ids) == 0 || len(ids) > 20 {
		return errors.New("每次请选择 1–20 个历史快照")
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.instances[id] == nil {
		return errors.New("实例不存在")
	}
	if m.active[id] != "" || m.processes[id] != nil {
		return errors.New("停止实例并等待任务结束后再清理")
	}
	report, _, e := m.scanSnapshots(id, false, false)
	if e != nil {
		return e
	}
	if report.ReadOnly {
		return errors.New(report.Error)
	}
	if report.Revision != revision {
		return errors.New("快照列表发生变化，请刷新后重新确认")
	}
	selected := []Snapshot{}
	seen := map[string]bool{}
	for _, key := range ids {
		if !validID(key) || seen[key] {
			return errors.New("快照选择无效")
		}
		seen[key] = true
		found := false
		for _, row := range report.Entries {
			if row.ID == key {
				found = true
				if !row.CanDelete {
					return errors.New("所选快照受保护、正在使用或需要检查")
				}
				if e = safeSnapshotPath(m.config.Root, row.path); e != nil {
					return e
				}
				selected = append(selected, row)
			}
		}
		if !found {
			return errors.New("快照已不在当前列表")
		}
	}
	// Every absolute target is resolved from the scoped inventory and checked
	// above, before any recursive deletion. Never accept a renderer path.
	for _, row := range selected {
		if row.Kind == "backup" {
			e = os.Remove(row.path)
		} else {
			e = os.RemoveAll(row.path)
		}
		if e != nil {
			return errors.New("部分清理未完成；当前进度与受保护快照保留，请刷新检查")
		}
	}
	return nil
}
func (m *Manager) Backup(id string) (Task, error) {
	return m.task(id, "backup", func(t *Task) error {
		m.mu.Lock()
		installed := m.instances[id].Commit != ""
		m.mu.Unlock()
		if !installed {
			return errors.New("请先安装实例")
		}
		if e := safeSnapshotPath(m.config.Root, m.path(id)); e != nil {
			return errors.New("实例目录包含链接或无法读取，不创建快照")
		}
		if info, e := os.Lstat(filepath.Join(m.path(id), "app", "scripts", "backup.py")); e != nil || !info.Mode().IsRegular() {
			return errors.New("此本体未提供完整备份工具，请先选择兼容本体版本")
		}
		work := filepath.Join(m.path(id), "work-"+t.ID)
		if e := os.MkdirAll(work, 0700); e != nil {
			return e
		}
		defer os.RemoveAll(work)
		m.progress(t, 20, "在线备份数据库、素材与已安装模块")
		path := filepath.Join(work, "bundle.zip")
		if e := m.run(t, 8*time.Minute, filepath.Join(m.path(id), "app"), m.childEnv(id), m.installedPython(id), "scripts/backup.py", "--bundle", "--output", path); e != nil {
			return e
		}
		if !backupMetadata(path) {
			return errors.New("备份包格式未确认，不会发布为可选快照")
		}
		target := filepath.Join(m.path(id), "backups", "manual-"+t.ID+".zip")
		if e := os.MkdirAll(filepath.Dir(target), 0700); e != nil {
			return e
		}
		m.progress(t, 95, "确认备份完整并保存新快照")
		return os.Rename(path, target)
	})
}
