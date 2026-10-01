package engine

import (
	"archive/zip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"
)

var HTTPClient = &http.Client{Timeout: 4 * time.Minute}

func fetchJSON(url string, result any) error {
	ctx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()
	r, _ := http.NewRequestWithContext(ctx, "GET", url, nil)
	r.Header.Set("User-Agent", "Ember-Launcher/"+LauncherVersion)
	r.Header.Set("Accept", "application/vnd.github+json")
	res, e := HTTPClient.Do(r)
	if e != nil {
		return e
	}
	defer res.Body.Close()
	if res.StatusCode != 200 {
		return fmt.Errorf("GitHub 请求失败（%d）；检查网络或稍后重试", res.StatusCode)
	}
	return json.NewDecoder(io.LimitReader(res.Body, 2<<20)).Decode(result)
}
func Resolve(channel string) (Release, error) {
	if channel == "main" {
		var data struct {
			SHA string `json:"sha"`
		}
		if e := fetchJSON("https://api.github.com/repos/"+Repository+"/commits/main", &data); e != nil {
			return Release{}, e
		}
		if len(data.SHA) != 40 {
			return Release{}, errors.New("GitHub 提交信息无效")
		}
		return Release{Version: "main · " + data.SHA[:7], Commit: data.SHA, Source: "main", URL: "https://codeload.github.com/" + Repository + "/zip/" + data.SHA}, nil
	}
	if channel != "release" {
		return Release{}, errors.New("未知更新通道")
	}
	var releases []struct {
		Tag   string `json:"tag_name"`
		Draft bool   `json:"draft"`
	}
	if e := fetchJSON("https://api.github.com/repos/"+Repository+"/releases?per_page=20", &releases); e != nil {
		return Release{}, e
	}
	for _, r := range releases {
		if r.Draft || !strings.HasPrefix(r.Tag, "v") || strings.HasPrefix(r.Tag, "plugin-") {
			continue
		}
		var commit struct {
			SHA string `json:"sha"`
		}
		if e := fetchJSON("https://api.github.com/repos/"+Repository+"/commits/"+url.PathEscape(r.Tag), &commit); e != nil {
			return Release{}, e
		}
		if len(commit.SHA) != 40 {
			return Release{}, errors.New("版本提交无效")
		}
		return Release{Version: r.Tag, Commit: commit.SHA, Source: "release", URL: "https://codeload.github.com/" + Repository + "/zip/" + commit.SHA}, nil
	}
	return Release{}, errors.New("暂时没有可安装的应用版本，请选择最新源码通道")
}
func (m *Manager) Check(id string) (Release, error) {
	m.mu.Lock()
	i := m.instances[id]
	if i == nil {
		m.mu.Unlock()
		return Release{}, errors.New("实例不存在")
	}
	channel := i.Channel
	m.mu.Unlock()
	if channel == "bundled" {
		var manifest struct {
			Version string `json:"app_version"`
		}
		b, e := os.ReadFile(filepath.Join(m.config.BundledSource, "launcher-manifest.json"))
		if e != nil {
			return Release{}, e
		}
		if e = json.Unmarshal(b, &manifest); e != nil {
			return Release{}, e
		}
		return Release{Version: manifest.Version, Commit: m.config.BundledCommit, Source: "bundled"}, nil
	}
	return Resolve(channel)
}
func Download(url, path, expected string, max int64, progress func(int64, int64)) error {
	if !strings.HasPrefix(url, "https://") {
		return errors.New("下载只允许 HTTPS")
	}
	req, _ := http.NewRequest("GET", url, nil)
	req.Header.Set("User-Agent", "Ember-Launcher/"+LauncherVersion)
	response, e := HTTPClient.Do(req)
	if e != nil {
		return e
	}
	defer response.Body.Close()
	if response.StatusCode != 200 {
		return fmt.Errorf("下载失败（HTTP %d）", response.StatusCode)
	}
	if response.ContentLength > max {
		return errors.New("下载超过大小限制")
	}
	if e = os.MkdirAll(filepath.Dir(path), 0700); e != nil {
		return e
	}
	temp := path + ".part"
	f, e := os.OpenFile(temp, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0600)
	if e != nil {
		return e
	}
	defer os.Remove(temp)
	hash := sha256.New()
	buf := make([]byte, 64*1024)
	var size int64
	for {
		n, err := response.Body.Read(buf)
		if n > 0 {
			size += int64(n)
			if size > max {
				f.Close()
				return errors.New("下载超过大小限制")
			}
			if _, e = f.Write(buf[:n]); e != nil {
				f.Close()
				return e
			}
			hash.Write(buf[:n])
			if progress != nil {
				progress(size, response.ContentLength)
			}
		}
		if err == io.EOF {
			break
		}
		if err != nil {
			f.Close()
			return err
		}
	}
	if e = f.Close(); e != nil {
		return e
	}
	if expected != "" && hex.EncodeToString(hash.Sum(nil)) != expected {
		return errors.New("下载校验失败，文件没有被执行")
	}
	return os.Rename(temp, path)
}
func Extract(source, destination string) error {
	r, e := zip.OpenReader(source)
	if e != nil {
		return e
	}
	defer r.Close()
	if len(r.File) > 6000 {
		return errors.New("文件数量过多")
	}
	var expanded uint64
	seen := map[string]bool{}
	for _, f := range r.File {
		expanded += f.UncompressedSize64
		if expanded > 300<<20 {
			return errors.New("解压内容超过 300 MiB")
		}
		name := f.Name
		if strings.Contains(name, "\\") || strings.Contains(name, ":") || strings.HasPrefix(name, "/") || f.Mode()&os.ModeSymlink != 0 {
			return errors.New("压缩包包含不安全路径")
		}
		clean := filepath.Clean(filepath.FromSlash(name))
		if clean == ".." || strings.HasPrefix(clean, ".."+string(filepath.Separator)) {
			return errors.New("压缩包路径越界")
		}
		if seen[clean] {
			return errors.New("压缩包包含重复文件")
		}
		seen[clean] = true
		target := filepath.Join(destination, clean)
		if f.FileInfo().IsDir() {
			if e = os.MkdirAll(target, 0700); e != nil {
				return e
			}
			continue
		}
		if e = os.MkdirAll(filepath.Dir(target), 0700); e != nil {
			return e
		}
		reader, err := f.Open()
		if err != nil {
			return err
		}
		out, err := os.OpenFile(target, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
		if err != nil {
			reader.Close()
			return err
		}
		_, err = io.Copy(out, io.LimitReader(reader, 300<<20))
		reader.Close()
		closeErr := out.Close()
		if err != nil {
			return err
		}
		if closeErr != nil {
			return closeErr
		}
	}
	return nil
}
func copyTree(src, dst string) error {
	return filepath.WalkDir(src, func(path string, d os.DirEntry, e error) error {
		if e != nil {
			return e
		}
		rel, e := filepath.Rel(src, path)
		if e != nil {
			return e
		}
		if d.IsDir() && (d.Name() == ".git" || d.Name() == "data" || d.Name() == "node_modules" || d.Name() == "__pycache__" || d.Name() == ".venv" || d.Name() == ".pytest_cache") {
			return filepath.SkipDir
		}
		if d.Type()&os.ModeSymlink != 0 {
			return errors.New("来源包含符号链接")
		}
		target := filepath.Join(dst, rel)
		if d.IsDir() {
			return os.MkdirAll(target, 0700)
		}
		if d.Name() == ".env" {
			return nil
		}
		b, e := os.ReadFile(path)
		if e != nil {
			return e
		}
		return os.WriteFile(target, b, 0600)
	})
}
