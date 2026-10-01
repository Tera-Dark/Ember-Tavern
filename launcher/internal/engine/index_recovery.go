package engine

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

// Raw records stay in the private index, never in an API response. Keeping them
// here prevents an unrelated Create/Configure/update from discarding legacy rows.
type indexRecord struct {
	EntryID    string          `json:"entry_id"`
	Reason     string          `json:"reason"`
	Record     json.RawMessage `json:"record"`
	RestoredID string          `json:"restored_id,omitempty"`
	Duplicate  bool            `json:"duplicate,omitempty"`
}

type IndexIssue struct {
	EntryID    string `json:"entry_id"`
	LegacyID   string `json:"legacy_id"`
	Name       string `json:"name"`
	Reason     string `json:"reason"`
	CanRecover bool   `json:"can_recover"`
	RestoredID string `json:"restored_id,omitempty"`
}
type IndexRecovery struct {
	Entries    []IndexIssue `json:"entries"`
	BackupName string       `json:"backup_name,omitempty"`
	Pending    int          `json:"pending"`
}

var legacySegment = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`)
var backupName = regexp.MustCompile(`^launcher-[a-f0-9]{64}\.json$`)

func safeLegacyID(value string) bool {
	if !legacySegment.MatchString(value) {
		return false
	}
	// Windows aliases must also be rejected when reviewing the index on Linux.
	switch strings.ToUpper(value) {
	case "CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$":
		return false
	}
	upper := strings.ToUpper(value)
	if len(upper) == 4 && (strings.HasPrefix(upper, "COM") || strings.HasPrefix(upper, "LPT")) && upper[3] >= '0' && upper[3] <= '9' {
		return false
	}
	return true
}

func validIndexInstance(row Instance) bool {
	return checkName(row.Name) == nil && row.Port >= 1024 && row.Port <= 65535 &&
		(row.Channel == "bundled" || row.Channel == "main" || row.Channel == "release") &&
		(row.RecoveredFromID == "" || safeLegacyID(row.RecoveredFromID))
}

func (m *Manager) loadIndex() error {
	path := filepath.Join(m.config.Root, "launcher.json")
	file, e := os.Open(path)
	if os.IsNotExist(e) {
		return nil
	}
	if e != nil {
		return e
	}
	defer file.Close()
	b, e := io.ReadAll(io.LimitReader(file, (4<<20)+1))
	if e != nil {
		return e
	}
	if len(b) > 4<<20 {
		return errors.New("启动器索引超过 4 MiB；请保留数据并人工检查")
	}
	var wire struct {
		Schema      int               `json:"schema"`
		Instances   []json.RawMessage `json:"instances"`
		Quarantined []indexRecord     `json:"quarantined"`
		IndexBackup string            `json:"index_backup"`
	}
	if json.Unmarshal(b, &wire) != nil {
		return errors.New("启动器索引损坏；请保留数据并恢复 launcher.json")
	}
	if wire.Schema != 0 && wire.Schema != 1 {
		return errors.New("启动器索引来自不支持的版本；不会覆盖，请使用对应版本")
	}
	if wire.IndexBackup != "" && !backupName.MatchString(wire.IndexBackup) {
		return errors.New("索引备份引用无效；请保留索引人工检查")
	}
	seen := map[string]bool{}
	for _, entry := range wire.Quarantined {
		if !validID(entry.EntryID) || seen[entry.EntryID] || !json.Valid(entry.Record) || (entry.RestoredID != "" && !validID(entry.RestoredID)) {
			return errors.New("隔离记录损坏；不会覆盖原索引")
		}
		seen[entry.EntryID] = true
	}
	m.indexOriginal = b
	m.indexBackup = wire.IndexBackup
	m.quarantined = wire.Quarantined
	seenIDs := map[string]bool{}
	for pos, raw := range wire.Instances {
		var row Instance
		reason := ""
		duplicate := false
		if json.Unmarshal(raw, &row) != nil {
			reason = "旧记录字段格式无效"
		} else if row.ID != "" && seenIDs[row.ID] {
			reason = "实例 ID 重复；保留首条，不能自动恢复重复目录"
			duplicate = true
		} else if !validID(row.ID) {
			reason = "旧实例 ID 不符合当前安全格式"
		} else if m.instances[row.ID] != nil {
			reason = "实例 ID 重复；保留首条，不能自动恢复重复目录"
		} else if !validIndexInstance(row) {
			reason = "旧实例名称、端口、通道或恢复关联无效"
		}
		if row.ID != "" {
			seenIDs[row.ID] = true
		}
		if reason != "" {
			sum := sha256.Sum256(append([]byte(fmt.Sprintf("%d:", pos)), raw...))
			entryID := hex.EncodeToString(sum[:16])
			if seen[entryID] {
				return errors.New("隔离记录 ID 冲突；请保留索引人工检查")
			}
			seen[entryID] = true
			m.quarantined = append(m.quarantined, indexRecord{EntryID: entryID, Reason: reason, Duplicate: duplicate, Record: append(json.RawMessage(nil), raw...)})
			continue
		}
		x := row
		m.instances[row.ID] = &x
	}
	return nil
}

// The backup is byte-exact and write-once, before any index mutation. Load alone
// is read-only. An unavailable or altered backup blocks a write, not a warning.
func (m *Manager) backupIndexLocked() error {
	if m.indexBackup != "" {
		dir := filepath.Join(m.config.Root, "index-backups")
		if e := plainDirectory(dir, false); e != nil {
			return errors.New("旧索引备份目录不可用；不会覆盖索引")
		}
		path := filepath.Join(dir, m.indexBackup)
		info, e := os.Lstat(path)
		if e != nil || !info.Mode().IsRegular() || info.Size() > 4<<20 {
			return errors.New("旧索引备份缺失或不是普通小型文件；不会覆盖索引")
		}
		b, e := os.ReadFile(path)
		sum := sha256.Sum256(b)
		if e != nil || "launcher-"+hex.EncodeToString(sum[:])+".json" != m.indexBackup {
			return errors.New("旧索引备份校验失败；不会覆盖索引")
		}
		return nil
	}
	if len(m.quarantined) == 0 || len(m.indexOriginal) == 0 {
		return nil
	}
	sum := sha256.Sum256(m.indexOriginal)
	name := "launcher-" + hex.EncodeToString(sum[:]) + ".json"
	dir := filepath.Join(m.config.Root, "index-backups")
	if e := plainDirectory(dir, true); e != nil {
		return fmt.Errorf("不能安全备份旧索引：%w", e)
	}
	path := filepath.Join(dir, name)
	f, e := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if os.IsExist(e) {
		info, err := os.Lstat(path)
		if err != nil || !info.Mode().IsRegular() {
			return errors.New("索引备份路径不是普通文件")
		}
		existing, err := os.ReadFile(path)
		if err != nil || string(existing) != string(m.indexOriginal) {
			return errors.New("索引备份已被修改；不会覆盖")
		}
	} else if e != nil {
		return fmt.Errorf("旧索引备份失败，未修改索引：%w", e)
	} else {
		_, e = f.Write(m.indexOriginal)
		if e == nil {
			e = f.Sync()
		}
		closeErr := f.Close()
		if e != nil || closeErr != nil {
			_ = os.Remove(path)
			return errors.New("旧索引备份未完成，未修改索引")
		}
	}
	m.indexBackup = name
	return nil
}

func plainDirectory(path string, create bool) error {
	info, e := os.Lstat(path)
	if os.IsNotExist(e) && create {
		return os.Mkdir(path, 0700)
	}
	if e != nil {
		return e
	}
	if !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		return errors.New("目录缺失或是链接；自动恢复已拒绝")
	}
	return nil
}

func (m *Manager) legacyDirectory(row Instance) (string, error) {
	// Never join an unsafe index ID to a filesystem path, even to check existence.
	if !safeLegacyID(row.ID) {
		return "", errors.New("旧 ID 不是安全的单层目录名；请使用人工恢复流程")
	}
	if m.instances[row.ID] != nil {
		return "", errors.New("旧目录已被有效实例使用，不能自动复制重复记录")
	}
	for _, current := range m.instances {
		if current.RecoveredFromID == row.ID {
			return "", errors.New("这个旧目录已经复制恢复；不会重复生成实例")
		}
	}
	base := filepath.Join(m.config.Root, "instances")
	if e := plainDirectory(base, false); e != nil {
		return "", e
	}
	source := filepath.Join(base, row.ID)
	if e := plainDirectory(source, false); e != nil {
		return "", e
	}
	if e := plainDirectory(filepath.Join(source, "data"), false); e != nil {
		return "", e
	}
	return source, nil
}

func (m *Manager) IndexRecovery() IndexRecovery {
	m.mu.Lock()
	defer m.mu.Unlock()
	result := IndexRecovery{Entries: []IndexIssue{}, BackupName: m.indexBackup}
	for _, entry := range m.quarantined {
		var row Instance
		parseErr := json.Unmarshal(entry.Record, &row)
		issue := IndexIssue{EntryID: entry.EntryID, LegacyID: displayText(row.ID), Name: displayText(row.Name), Reason: entry.Reason, RestoredID: entry.RestoredID}
		if entry.RestoredID == "" {
			result.Pending++
			if parseErr == nil && !entry.Duplicate && validIndexInstance(row) {
				_, e := m.legacyDirectory(row)
				issue.CanRecover = e == nil
			}
		}
		result.Entries = append(result.Entries, issue)
	}
	return result
}
func displayText(value string) string {
	clean := strings.Map(func(r rune) rune {
		if r < 32 || r == 127 {
			return -1
		}
		return r
	}, value)
	runes := []rune(clean)
	if len(runes) > 96 {
		clean = string(runes[:96]) + "…"
	}
	return clean
}
func (m *Manager) BundledCommit() string { return m.config.BundledCommit }

func (m *Manager) RecoverIndexEntry(entryID string, confirmStopped bool) (View, error) {
	if !validID(entryID) {
		return View{}, errors.New("无效隔离记录 ID")
	}
	if !confirmStopped {
		return View{}, errors.New("请先关闭旧启动器与酒馆服务，并确认后恢复")
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.closing {
		return View{}, errors.New("启动器正在退出")
	}
	var entry *indexRecord
	for pos := range m.quarantined {
		if m.quarantined[pos].EntryID == entryID {
			entry = &m.quarantined[pos]
			break
		}
	}
	if entry == nil {
		return View{}, errors.New("隔离记录不存在")
	}
	if entry.Duplicate {
		return View{}, errors.New("重复的旧记录不能自动恢复；请人工检查索引")
	}
	if entry.RestoredID != "" {
		if m.instances[entry.RestoredID] == nil {
			return View{}, errors.New("恢复目标不在索引中；请保留备份人工检查")
		}
		return m.viewLocked(entry.RestoredID), nil // Lost response/retry is idempotent.
	}
	if len(m.instances) >= 24 {
		return View{}, errors.New("最多管理 24 个实例")
	}
	var old Instance
	if json.Unmarshal(entry.Record, &old) != nil || !validIndexInstance(old) {
		return View{}, errors.New("旧实例元数据无效；请使用人工恢复流程")
	}
	source, e := m.legacyDirectory(old)
	if e != nil {
		return View{}, e
	}
	if e = availablePort(old.Port); e != nil {
		return View{}, errors.New("旧端口仍被占用；请先确认旧服务已停止")
	}
	for _, row := range m.instances {
		if row.Port == old.Port {
			return View{}, errors.New("旧端口已分配给另一实例；请人工确认目录与实例对应关系")
		}
	}
	newID := ident()
	destination := m.path(newID)
	if e = os.Mkdir(destination, 0700); e != nil {
		return View{}, e
	}
	keep := false
	defer func() {
		if !keep {
			_ = os.RemoveAll(destination)
		}
	}()
	// Copy, do not move/delete the original. Code, environments, update journals
	// and python-path are deliberately not adopted from a legacy directory.
	if e = copyRecoveryData(filepath.Join(source, "data"), filepath.Join(destination, "data")); e != nil {
		return View{}, e
	}
	settingsPath := filepath.Join(source, "settings.json")
	if info, err := os.Lstat(settingsPath); err == nil {
		if !info.Mode().IsRegular() || info.Size() > 48<<10 {
			return View{}, errors.New("旧配置不是普通小型文件；请人工检查")
		}
		b, err := os.ReadFile(settingsPath)
		if err != nil {
			return View{}, err
		}
		var values map[string]string
		if json.Unmarshal(b, &values) != nil {
			return View{}, errors.New("旧配置格式无效，恢复已取消")
		}
		checked := map[string]string{}
		if e = applySettings(checked, values); e != nil {
			return View{}, fmt.Errorf("旧配置需要人工检查：%w", e)
		}
		if e = atomicJSON(filepath.Join(destination, "settings.json"), checked); e != nil {
			return View{}, e
		}
	} else if !os.IsNotExist(err) {
		return View{}, err
	}
	channel := old.Channel
	if m.config.BundledSource != "" {
		channel = "bundled"
	} else if channel == "bundled" {
		return View{}, errors.New("需要提供打包本体后再恢复")
	}
	row := &Instance{ID: newID, Name: old.Name, Port: old.Port, LAN: old.LAN, Channel: channel, RecoveredFromID: old.ID}
	m.instances[newID] = row
	entry.RestoredID = newID
	if e = m.saveLocked(); e != nil {
		delete(m.instances, newID)
		entry.RestoredID = ""
		return View{}, e
	}
	keep = true
	return m.viewLocked(newID), nil
}

func copyRecoveryData(src, dst string) error {
	var size int64
	count := 0
	// Preflight before copying, bounded and without following symlinks. WAL/SHM
	// are included: the caller must confirm that the old service is stopped.
	if e := filepath.WalkDir(src, func(path string, d os.DirEntry, e error) error {
		if e != nil {
			return e
		}
		info, e := d.Info()
		if e != nil {
			return e
		}
		if d.Type()&os.ModeSymlink != 0 || (!info.IsDir() && !info.Mode().IsRegular()) {
			return errors.New("旧数据含链接或特殊文件，自动恢复已拒绝")
		}
		count++
		size += info.Size()
		if count > 20000 || size > 1<<30 {
			return errors.New("旧数据超过自动恢复限制（1 GiB / 20000 项）；请人工恢复")
		}
		return nil
	}); e != nil {
		return e
	}
	var copied int64
	return filepath.WalkDir(src, func(path string, d os.DirEntry, e error) error {
		if e != nil {
			return e
		}
		if d.Type()&os.ModeSymlink != 0 {
			return errors.New("复制期间出现链接，恢复已取消")
		}
		rel, e := filepath.Rel(src, path)
		if e != nil {
			return e
		}
		target := filepath.Join(dst, rel)
		if d.IsDir() {
			return os.Mkdir(target, 0700)
		}
		info, e := os.Lstat(path)
		if e != nil || !info.Mode().IsRegular() {
			return errors.New("复制期间文件类型变化，恢复已取消")
		}
		in, e := os.Open(path)
		if e != nil {
			return e
		}
		defer in.Close()
		out, e := os.OpenFile(target, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
		if e != nil {
			return e
		}
		n, copyErr := io.Copy(out, io.LimitReader(in, (1<<30)-copied+1))
		copied += n
		closeErr := out.Close()
		_ = in.Close()
		if copyErr != nil {
			return copyErr
		}
		if closeErr != nil {
			return closeErr
		}
		if copied > 1<<30 {
			return errors.New("复制期间数据超过限制，恢复已取消")
		}
		return nil
	})
}
