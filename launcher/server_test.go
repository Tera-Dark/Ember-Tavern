package main

import (
	"ember-tavern/launcher/internal/engine"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func testAPI(t *testing.T) *API {
	m, e := engine.New(engine.Config{Root: t.TempDir()})
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(m.Close)
	return &API{Manager: m, Token: "test-nonce", Open: func(string) error { return nil }}
}
func request(a *API, method, path, body, host, origin, cookie string, header bool) *httptest.ResponseRecorder {
	r := httptest.NewRequest(method, "http://127.0.0.1:8765"+path, strings.NewReader(body))
	r.Host = host
	if origin != "" {
		r.Header.Set("Origin", origin)
	}
	if header {
		r.Header.Set("X-Ember-Launcher", "1")
	}
	if cookie != "" {
		r.AddCookie(&http.Cookie{Name: "ember-launcher", Value: cookie})
	}
	w := httptest.NewRecorder()
	a.Handler().ServeHTTP(w, r)
	return w
}
func TestRequiresLocalAuthentication(t *testing.T) {
	a := testAPI(t)
	w := request(a, "GET", "/api/state", "", "127.0.0.1:8765", "", "", false)
	if w.Code != 401 {
		t.Fatal(w.Code)
	}
	w = request(a, "GET", "/api/state", "", "127.0.0.1:8765", "", "test-nonce", false)
	if w.Code != 200 {
		t.Fatal(w.Code)
	}
}
func TestOriginAndHostRejected(t *testing.T) {
	a := testAPI(t)
	w := request(a, "POST", "/api/instances", `{"name":"test","channel":"main"}`, "127.0.0.1:8765", "https://evil.example", "test-nonce", true)
	if w.Code != 403 {
		t.Fatal(w.Code)
	}
	w = request(a, "GET", "/api/state", "", "evil.example", "", "test-nonce", false)
	if w.Code != 403 {
		t.Fatal(w.Code)
	}
}
func TestMutationNeedsHeader(t *testing.T) {
	a := testAPI(t)
	w := request(a, "POST", "/api/instances", `{"name":"test","channel":"main"}`, "127.0.0.1:8765", "", "test-nonce", false)
	if w.Code != 403 {
		t.Fatal(w.Code)
	}
}
func TestBootstrapAndCreate(t *testing.T) {
	a := testAPI(t)
	w := request(a, "GET", "/bootstrap?key=test-nonce", "", "127.0.0.1:8765", "", "", false)
	if w.Code != 303 || len(w.Result().Cookies()) != 1 || !w.Result().Cookies()[0].HttpOnly {
		t.Fatal("bootstrap")
	}
	w = request(a, "POST", "/api/instances", `{"name":"雾港","channel":"main","port":8190,"lan":false,"start":false}`, "127.0.0.1:8765", "http://127.0.0.1:8765", "test-nonce", true)
	if w.Code != 201 {
		t.Fatal(w.Code, w.Body.String())
	}
}
