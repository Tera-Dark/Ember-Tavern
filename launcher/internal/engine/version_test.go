package engine

import "testing"

func TestMinimumVersionIncludesPrereleaseOrdering(t *testing.T) {
	for _, row := range []struct {
		current, minimum string
		ok               bool
	}{
		{"0.2.0-beta.1", "0.2.0-beta.2", false}, {"0.2.0-beta.2", "0.2.0-beta.1", true},
		{"0.2.0-beta.2", "0.2.0-beta.10", false}, {"0.2.0-beta.10", "0.2.0-beta.2", true},
		{"0.2.0-rc.1", "0.2.0-beta.9", true}, {"0.2.0-beta.2", "0.2.0", false},
		{"0.2.0", "0.2.0-beta.2", true}, {"0.3.0-beta.1", "0.2.0", true},
		{"0.2.0-beta.2+build.1", "0.2.0-beta.2+build.2", true},
	} {
		actual, e := versionAtLeast(row.current, row.minimum)
		if e != nil || actual != row.ok {
			t.Fatalf("%s >= %s: %v, %v", row.current, row.minimum, actual, e)
		}
	}
	for _, value := range []string{"0.2", "v0.2.0", "0.02.0", "0.2.0-beta.02", "0.2.0junk", "0.2.0-", "1.2.3.4"} {
		if _, e := versionAtLeast(LauncherVersion, value); e == nil {
			t.Fatal("invalid version accepted", value)
		}
	}
}
