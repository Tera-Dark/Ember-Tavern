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
	"regexp"
	"sort"
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
	tags, e := ReleaseTags()
	if e != nil {
		return Release{}, e
	}
	if len(tags) == 0 {
		return Release{}, errors.New("GitHub 暂无已发布版本")
	}
	return ResolveTag(tags[0].Tag)
}

var commitPattern = regexp.MustCompile(`^[a-f0-9]{40}$`)

func validReleaseTag(tag string) bool {
	version := strings.TrimPrefix(tag, "desktop-v")
	if version == tag {
		version = strings.TrimPrefix(tag, "v")
		if version == tag {
			return false
		}
	}
	_, e := parseVersion(version)
	return e == nil && len(tag) <= 80
}

type ReleaseTag struct {
	Tag         string `json:"tag"`
	Version     string `json:"version"`
	PublishedAt string `json:"published_at"`
}

// List all pages: /latest excludes the beta releases used by this project.
func ReleaseTags() ([]ReleaseTag, error) {
	result := []ReleaseTag{}
	for page := 1; page <= 20; page++ {
		var rows []struct {
			Tag       string `json:"tag_name"`
			Draft     bool   `json:"draft"`
			Published string `json:"published_at"`
		}
		if e := fetchJSON(fmt.Sprintf("https://api.github.com/repos/%s/releases?per_page=100&page=%d", Repository, page), &rows); e != nil {
			return nil, e
		}
		for _, r := range rows {
			if r.Draft || !validReleaseTag(r.Tag) {
				continue
			}
			v := strings.TrimPrefix(strings.TrimPrefix(r.Tag, "desktop-"), "v")
			result = append(result, ReleaseTag{Tag: r.Tag, Version: v, PublishedAt: r.Published})
		}
		if len(rows) < 100 {
			// Desktop and host have independent version sequences. Desktop
			// releases are the supported integrated product; legacy host tags follow.
			sort.SliceStable(result, func(i, j int) bool {
				a, b := result[i], result[j]
				ad, bd := strings.HasPrefix(a.Tag, "desktop-"), strings.HasPrefix(b.Tag, "desktop-")
				if ad != bd {
					return ad
				}
				ge, _ := versionAtLeast(a.Version, b.Version)
				eq, _ := versionAtLeast(b.Version, a.Version)
				if ge && !eq {
					return true
				}
				if eq && ge {
					return a.PublishedAt > b.PublishedAt
				}
				return false
			})
			return result, nil
		}
	}
	return nil, errors.New("版本目录超过查询上限，请稍后重试或联系维护者")
}
func ResolveTag(tag string) (Release, error) {
	if !validReleaseTag(tag) {
		return Release{}, errors.New("无效发行版本")
	}
	var published struct {
		Tag       string `json:"tag_name"`
		Draft     bool   `json:"draft"`
		Published string `json:"published_at"`
	}
	if e := fetchJSON("https://api.github.com/repos/"+Repository+"/releases/tags/"+url.PathEscape(tag), &published); e != nil {
		return Release{}, e
	}
	if published.Draft || published.Tag != tag {
		return Release{}, errors.New("版本尚未公开发布")
	}
	var commit struct {
		SHA string `json:"sha"`
	}
	if e := fetchJSON("https://api.github.com/repos/"+Repository+"/commits/"+url.PathEscape(tag), &commit); e != nil {
		return Release{}, e
	}
	if !commitPattern.MatchString(commit.SHA) {
		return Release{}, errors.New("版本提交无效")
	}
	var manifest struct {
		Format  string `json:"format"`
		Version string `json:"app_version"`
	}
	if e := fetchJSON("https://raw.githubusercontent.com/"+Repository+"/"+commit.SHA+"/launcher-manifest.json", &manifest); e != nil {
		return Release{}, e
	}
	if _, e := parseVersion(manifest.Version); e != nil || manifest.Format != "ember-deploy/v1" {
		return Release{}, errors.New("版本缺少有效宿主部署清单")
	}
	return Release{Version: manifest.Version, Commit: commit.SHA, Source: "release", Tag: tag, PublishedAt: published.Published, URL: "https://codeload.github.com/" + Repository + "/zip/" + commit.SHA}, nil
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
		channel = "release"
	}
	r, e := m.resolveCached(channel)
	m.mu.Lock()
	defer m.mu.Unlock()
	u := &UpdateStatus{CheckedAt: timestamp()}
	if e != nil {
		u.Error = e.Error()
	} else {
		u.Latest = &r
		current := m.instances[id]
		newer := r.Commit != current.Commit
		if channel != "main" {
			ge, err := releaseAtLeastCurrent(r, *current)
			if err == nil {
				newer = ge && newer
			}
		}
		u.Suppressed = current.IgnoredUpdate == r.Commit
		u.Available = newer && !u.Suppressed && current.Commit != ""
	}
	m.updates[id] = u
	return r, e
}

// Desktop releases may carry the same host version while changing the launcher
// or source. Compare their release tags before treating an older source as an
// automatic update; explicit switch-version still permits a downgrade.
func releaseAtLeastCurrent(release Release, current Instance) (bool, error) {
	if validReleaseTag(release.Tag) && validReleaseTag(current.VersionTag) && strings.HasPrefix(release.Tag, "desktop-") == strings.HasPrefix(current.VersionTag, "desktop-") {
		return versionAtLeast(strings.TrimPrefix(strings.TrimPrefix(release.Tag, "desktop-"), "v"), strings.TrimPrefix(strings.TrimPrefix(current.VersionTag, "desktop-"), "v"))
	}
	return versionAtLeast(strings.TrimPrefix(release.Version, "v"), strings.TrimPrefix(current.Version, "v"))
}

type releaseCache struct {
	release Release
	at      time.Time
	err     error
}

func (m *Manager) resolveCached(channel string) (Release, error) {
	// A shared cache prevents a 24-instance desktop from exhausting GitHub's
	// unauthenticated quota at every startup. Failures remain retryable.
	m.remoteMu.Lock()
	defer m.remoteMu.Unlock()
	if cached, ok := m.remoteCache[channel]; ok {
		age := 5 * time.Minute
		if cached.err != nil {
			age = 30 * time.Second
		}
		if time.Since(cached.at) < age {
			return cached.release, cached.err
		}
	}
	r, e := Resolve(channel)
	if m.remoteCache == nil {
		m.remoteCache = map[string]releaseCache{}
	}
	m.remoteCache[channel] = releaseCache{release: r, at: time.Now(), err: e}
	return r, e
}
func Download(url, path, expected string, max int64, progress func(int64, int64)) error {
	return DownloadContext(context.Background(), url, path, expected, max, progress)
}
func DownloadContext(ctx context.Context, url, path, expected string, max int64, progress func(int64, int64)) error {
	if !strings.HasPrefix(url, "https://") {
		return errors.New("下载只允许 HTTPS")
	}
	req, e := http.NewRequestWithContext(ctx, "GET", url, nil)
	if e != nil {
		return e
	}
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
		if e = ctx.Err(); e != nil {
			f.Close()
			return e
		}
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
			// Read may return final bytes and EOF together. Cancellation can
			// also make a remote stream end normally; EOF is not consent to commit.
			if e = ctx.Err(); e != nil {
				f.Close()
				return e
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
	if e = ctx.Err(); e != nil {
		return e
	}
	if expected != "" && hex.EncodeToString(hash.Sum(nil)) != expected {
		return errors.New("下载校验失败，文件没有被执行")
	}
	if e = ctx.Err(); e != nil {
		return e
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
