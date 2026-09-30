package engine

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
)

type updateJournal struct {
	Prior    Instance `json:"prior"`
	Python   string   `json:"python"`
	HadApp   bool     `json:"had_app"`
	DataSwap bool     `json:"data_swap"`
}

func (m *Manager) recover(id string) error {
	root := m.path(id)
	path := filepath.Join(root, "update-journal.json")
	b, e := os.ReadFile(path)
	if os.IsNotExist(e) {
		return nil
	}
	if e != nil {
		return e
	}
	var j updateJournal
	if e = json.Unmarshal(b, &j); e != nil {
		return errors.New("更新恢复记录损坏，请保留数据并联系维护者")
	}
	if j.Prior.ID != id {
		return errors.New("更新恢复记录与实例不匹配")
	}
	app := filepath.Join(root, "app")
	previous := filepath.Join(root, "previous-app")
	if _, e = os.Stat(previous); e == nil {
		_ = os.Rename(app, filepath.Join(root, "interrupted-app-"+ident()))
		if e = os.Rename(previous, app); e != nil {
			return e
		}
	} else if !j.HadApp {
		_ = os.Rename(app, filepath.Join(root, "interrupted-app-"+ident()))
	}
	data := filepath.Join(root, "data")
	previousData := filepath.Join(root, "previous-data")
	if j.DataSwap {
		if _, e = os.Stat(previousData); e == nil {
			_ = os.Rename(data, filepath.Join(root, "interrupted-data-"+ident()))
			if e = os.Rename(previousData, data); e != nil {
				return e
			}
		}
	}
	if e = os.WriteFile(filepath.Join(root, "python-path"), []byte(j.Python), 0600); e != nil {
		return e
	}
	old := j.Prior
	m.instances[id] = &old
	if e = m.saveLocked(); e != nil {
		return e
	}
	return os.Remove(path)
}
