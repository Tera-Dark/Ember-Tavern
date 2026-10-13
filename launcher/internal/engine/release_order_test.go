package engine

import "testing"

func TestSameHostVersionDoesNotMakeOlderDesktopSourceAnAutomaticUpdate(t *testing.T) {
	current := Instance{Version: "2.4.0-beta.1", VersionTag: "desktop-v0.2.0-beta.4"}
	older := Release{Version: "2.4.0-beta.1", Tag: "desktop-v0.2.0-beta.3"}
	if ge, e := releaseAtLeastCurrent(older, current); e != nil || ge {
		t.Fatal("older source offered as latest", e)
	}
	newer := Release{Version: "2.4.0-beta.1", Tag: "desktop-v0.2.0-beta.5"}
	if ge, e := releaseAtLeastCurrent(newer, current); e != nil || !ge {
		t.Fatal("newer launcher release hidden", e)
	}
	legacy := Instance{Version: "2.3.0-beta.2"}
	if ge, e := releaseAtLeastCurrent(older, legacy); e != nil || !ge {
		t.Fatal("legacy host comparison changed", e)
	}
}
