package main

import (
	"crypto/rand"
	"ember-tavern/launcher/internal/engine"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"io/fs"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

type API struct {
	Manager  *engine.Manager
	Preview  bool
	Token    string
	Open     func(string) error
	Shutdown func()
}

func nonce() string { b := make([]byte, 24); _, _ = rand.Read(b); return hex.EncodeToString(b) }
func answer(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}
func failure(w http.ResponseWriter, e error) { answer(w, 400, map[string]string{"error": e.Error()}) }
func decode(r *http.Request, v any) error {
	defer r.Body.Close()
	d := json.NewDecoder(io.LimitReader(r.Body, 48<<10))
	d.DisallowUnknownFields()
	return d.Decode(v)
}
func (a *API) authorized(r *http.Request) bool {
	if a.Preview {
		return true
	}
	c, e := r.Cookie("ember-launcher")
	return e == nil && c.Value == a.Token
}
func (a *API) Handler() http.Handler {
	mux := http.NewServeMux()
	web, _ := fs.Sub(assets, "ui")
	mux.HandleFunc("GET /bootstrap", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Query().Get("key") != a.Token {
			http.Error(w, "Forbidden", 403)
			return
		}
		http.SetCookie(w, &http.Cookie{Name: "ember-launcher", Value: a.Token, Path: "/", HttpOnly: true, SameSite: http.SameSiteStrictMode, MaxAge: 86400})
		http.Redirect(w, r, "/", 303)
	})
	mux.HandleFunc("POST /api/shutdown", func(w http.ResponseWriter, r *http.Request) {
		if a.Shutdown == nil {
			failure(w, errors.New("此引擎未提供关闭控制"))
			return
		}
		answer(w, 202, map[string]bool{"stopping": true})
		go a.Shutdown()
	})
	mux.HandleFunc("GET /api/state", func(w http.ResponseWriter, r *http.Request) {
		answer(w, 200, map[string]any{"launcher_version": engine.LauncherVersion, "repository": engine.RepositoryURL, "root": a.Manager.Root(), "platform": platformName(), "preview": a.Preview, "instances": a.Manager.List(), "tasks": a.Manager.Tasks(), "task_history_error": a.Manager.TaskHistoryError(), "index_recovery": a.Manager.IndexRecovery(), "bundled_commit": a.Manager.BundledCommit()})
	})
	mux.HandleFunc("POST /api/index-recovery/{entry}", func(w http.ResponseWriter, r *http.Request) {
		var v struct {
			ConfirmStopped bool `json:"confirm_stopped"`
		}
		if e := decode(r, &v); e != nil {
			failure(w, e)
			return
		}
		row, e := a.Manager.RecoverIndexEntry(r.PathValue("entry"), v.ConfirmStopped)
		if e != nil {
			failure(w, e)
			return
		}
		answer(w, 200, row)
	})
	mux.HandleFunc("POST /api/instances", func(w http.ResponseWriter, r *http.Request) {
		var v struct {
			Name    string `json:"name"`
			Channel string `json:"channel"`
			Port    int    `json:"port"`
			LAN     bool   `json:"lan"`
			Start   bool   `json:"start"`
		}
		if e := decode(r, &v); e != nil {
			failure(w, e)
			return
		}
		row, e := a.Manager.Create(v.Name, v.Channel, v.Port, v.LAN)
		if e != nil {
			failure(w, e)
			return
		}
		if v.Start {
			task, e := a.Manager.Install(row.ID, true)
			if e != nil {
				failure(w, e)
				return
			}
			answer(w, 202, map[string]any{"instance": row, "task": task})
			return
		}
		answer(w, 201, row)
	})
	mux.HandleFunc("GET /api/install-plan", func(w http.ResponseWriter, r *http.Request) {
		port, e := strconv.Atoi(r.URL.Query().Get("port"))
		if e != nil {
			failure(w, errors.New("端口需为整数"))
			return
		}
		plan, e := a.Manager.InstallationPlan(port)
		if e != nil {
			failure(w, e)
			return
		}
		answer(w, 200, plan)
	})
	mux.HandleFunc("PUT /api/instances/{id}", func(w http.ResponseWriter, r *http.Request) {
		var v struct {
			Name    string `json:"name"`
			Channel string `json:"channel"`
			Port    int    `json:"port"`
			LAN     bool   `json:"lan"`
		}
		if e := decode(r, &v); e != nil {
			failure(w, e)
			return
		}
		if e := a.Manager.Configure(r.PathValue("id"), v.Name, v.Channel, v.Port, v.LAN); e != nil {
			failure(w, e)
			return
		}
		answer(w, 200, map[string]bool{"saved": true})
	})
	mux.HandleFunc("POST /api/instances/{id}/{action}", func(w http.ResponseWriter, r *http.Request) {
		id := r.PathValue("id")
		action := r.PathValue("action")
		var task engine.Task
		var err error
		switch action {
		case "switch-version":
			var v struct {
				Tag string `json:"tag"`
			}
			if e := decode(r, &v); e != nil {
				failure(w, e)
				return
			}
			task, err = a.Manager.SwitchVersion(id, v.Tag)
		case "install":
			task, err = a.Manager.Install(id, true)
		case "start":
			task, err = a.Manager.Start(id)
		case "stop":
			task, err = a.Manager.Stop(id)
		case "update":
			task, err = a.Manager.Update(id)
		case "check":
			release, e := a.Manager.Check(id)
			if e != nil {
				failure(w, e)
				return
			}
			answer(w, 200, release)
			return
		case "open":
			view, e := a.Manager.Get(id)
			if e != nil {
				failure(w, e)
				return
			}
			if view.Status != "running" {
				failure(w, errors.New("请先启动实例"))
				return
			}
			if a.Preview {
				answer(w, 200, map[string]string{"url": view.URL})
				return
			}
			if e = a.Open(view.URL); e != nil {
				failure(w, e)
				return
			}
			answer(w, 200, map[string]bool{"opened": true})
			return
		case "folder":
			view, e := a.Manager.Get(id)
			if e != nil {
				failure(w, e)
				return
			}
			if a.Preview {
				answer(w, 200, map[string]string{"path": view.DataPath})
				return
			}
			if e = a.Open(view.DataPath); e != nil {
				failure(w, e)
				return
			}
			answer(w, 200, map[string]bool{"opened": true})
			return
		default:
			failure(w, errors.New("未知操作"))
			return
		}
		if err != nil {
			failure(w, err)
			return
		}
		answer(w, 202, task)
	})
	mux.HandleFunc("GET /api/releases", func(w http.ResponseWriter, r *http.Request) {
		rows, e := engine.ReleaseTags()
		if e != nil {
			failure(w, e)
			return
		}
		answer(w, 200, rows)
	})
	mux.HandleFunc("POST /api/tasks/{id}/cancel", func(w http.ResponseWriter, r *http.Request) {
		if e := a.Manager.CancelTask(r.PathValue("id")); e != nil {
			failure(w, e)
			return
		}
		answer(w, 202, map[string]bool{"cancel_requested": true})
	})
	mux.HandleFunc("POST /api/tasks/{id}/retry", func(w http.ResponseWriter, r *http.Request) {
		task, e := a.Manager.RetryTask(r.PathValue("id"))
		if e != nil {
			failure(w, e)
			return
		}
		answer(w, 202, task)
	})
	mux.HandleFunc("GET /api/instances/{id}/settings", func(w http.ResponseWriter, r *http.Request) {
		result, e := a.Manager.Settings(r.PathValue("id"))
		if e != nil {
			failure(w, e)
			return
		}
		answer(w, 200, result)
	})
	mux.HandleFunc("GET /api/instances/{id}/snapshots", func(w http.ResponseWriter, r *http.Request) {
		value, e := a.Manager.Snapshots(r.PathValue("id"))
		if e != nil {
			failure(w, e)
			return
		}
		answer(w, 200, value)
	})
	mux.HandleFunc("POST /api/instances/{id}/snapshot-restore", func(w http.ResponseWriter, r *http.Request) {
		var value struct {
			ID       string `json:"snapshot_id"`
			Revision string `json:"revision"`
			Name     string `json:"name"`
		}
		if e := decode(r, &value); e != nil {
			failure(w, e)
			return
		}
		task, e := a.Manager.RestoreSnapshot(r.PathValue("id"), value.ID, value.Revision, value.Name)
		if e != nil {
			failure(w, e)
			return
		}
		answer(w, 202, task)
	})
	mux.HandleFunc("PUT /api/instances/{id}/snapshot-policy", func(w http.ResponseWriter, r *http.Request) {
		var value struct {
			Revision   string          `json:"revision"`
			KeepLatest int             `json:"keep_latest"`
			Protected  map[string]bool `json:"protected"`
		}
		if e := decode(r, &value); e != nil {
			failure(w, e)
			return
		}
		if e := a.Manager.SetSnapshotPolicy(r.PathValue("id"), value.Revision, value.KeepLatest, value.Protected); e != nil {
			failure(w, e)
			return
		}
		answer(w, 200, map[string]bool{"saved": true})
	})
	mux.HandleFunc("POST /api/instances/{id}/snapshot-delete", func(w http.ResponseWriter, r *http.Request) {
		var value struct {
			Revision string   `json:"revision"`
			IDs      []string `json:"ids"`
			Confirm  bool     `json:"confirm_delete"`
		}
		if e := decode(r, &value); e != nil {
			failure(w, e)
			return
		}
		if e := a.Manager.DeleteSnapshots(r.PathValue("id"), value.Revision, value.IDs, value.Confirm); e != nil {
			failure(w, e)
			return
		}
		answer(w, 200, map[string]bool{"deleted": true})
	})
	mux.HandleFunc("POST /api/instances/{id}/snapshot-backup", func(w http.ResponseWriter, r *http.Request) {
		task, e := a.Manager.Backup(r.PathValue("id"))
		if e != nil {
			failure(w, e)
			return
		}
		answer(w, 202, task)
	})
	mux.HandleFunc("PUT /api/instances/{id}/settings", func(w http.ResponseWriter, r *http.Request) {
		var v map[string]string
		if e := decode(r, &v); e != nil {
			failure(w, e)
			return
		}
		if e := a.Manager.SaveSettings(r.PathValue("id"), v); e != nil {
			failure(w, e)
			return
		}
		answer(w, 200, map[string]bool{"saved": true})
	})
	mux.HandleFunc("POST /api/instances/{id}/plugin-install", func(w http.ResponseWriter, r *http.Request) {
		var v struct {
			Path  string `json:"path"`
			SHA   string `json:"sha256"`
			Trust bool   `json:"trust_backend"`
			Grant bool   `json:"grant_capabilities"`
		}
		if e := decode(r, &v); e != nil {
			failure(w, e)
			return
		}
		task, e := a.Manager.InstallPlugin(r.PathValue("id"), v.Path, v.SHA, v.Trust, v.Grant)
		if e != nil {
			failure(w, e)
			return
		}
		answer(w, 202, task)
	})
	mux.HandleFunc("POST /api/instances/{id}/creator", func(w http.ResponseWriter, r *http.Request) {
		var request engine.CreatorRequest
		if e := decode(r, &request); e != nil {
			failure(w, e)
			return
		}
		task, e := a.Manager.Creator(r.PathValue("id"), request)
		if e != nil {
			failure(w, e)
			return
		}
		answer(w, 202, task)
	})
	mux.HandleFunc("GET /api/creator-results/{id}", func(w http.ResponseWriter, r *http.Request) {
		result, e := a.Manager.CreatorResult(r.PathValue("id"))
		if e != nil {
			failure(w, e)
			return
		}
		answer(w, 200, result)
	})
	mux.HandleFunc("PUT /api/instances/{id}/runtime-settings", func(w http.ResponseWriter, r *http.Request) {
		var values map[string]string
		if e := decode(r, &values); e != nil {
			failure(w, e)
			return
		}
		if e := a.Manager.SetRuntimeSettings(r.PathValue("id"), values); e != nil {
			failure(w, e)
			return
		}
		answer(w, 200, map[string]bool{"applied": true})
	})
	mux.HandleFunc("GET /api/instances/{id}/logs", func(w http.ResponseWriter, r *http.Request) {
		if _, e := a.Manager.Get(r.PathValue("id")); e != nil {
			failure(w, e)
			return
		}
		answer(w, 200, map[string]any{"lines": a.Manager.Logs(r.PathValue("id"))})
	})
	mux.HandleFunc("POST /api/open-guide", func(w http.ResponseWriter, r *http.Request) {
		if !a.Preview {
			_ = a.Open(engine.RepositoryURL + "/blob/main/QUICKSTART.md")
		}
		answer(w, 200, map[string]bool{"opened": true})
	})
	mux.Handle("/", http.FileServer(http.FS(web)))
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("Referrer-Policy", "no-referrer")
		w.Header().Set("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
		// Preview can be embedded by the development platform; production window cannot.
		if a.Preview {
			w.Header().Set("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'")
		}
		if !a.Preview {
			host := strings.Split(r.Host, ":")[0]
			if host != "127.0.0.1" && host != "localhost" {
				http.Error(w, "Host rejected", 403)
				return
			}
		}
		if strings.HasPrefix(r.URL.Path, "/api/") {
			if !a.authorized(r) {
				http.Error(w, "Unauthorized", 401)
				return
			}
			if r.Method != "GET" {
				if r.Header.Get("X-Ember-Launcher") != "1" {
					http.Error(w, "Request rejected", 403)
					return
				}
				origin := r.Header.Get("Origin")
				if origin != "" && origin != "http://"+r.Host && origin != "https://"+r.Host {
					http.Error(w, "Origin rejected", 403)
					return
				}
			}
		}
		mux.ServeHTTP(w, r)
	})
}

var _ = os.ErrNotExist
var _ = filepath.Separator
var _ = time.Second
