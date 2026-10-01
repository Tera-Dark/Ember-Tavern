package engine

import (
	"errors"
	"regexp"
	"strconv"
	"strings"
)

var semverPattern = regexp.MustCompile(`^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$`)

type semanticVersion struct {
	core [3]int
	pre  []string
}

func parseVersion(value string) (semanticVersion, error) {
	var result semanticVersion
	parts := semverPattern.FindStringSubmatch(value)
	if parts == nil {
		return result, errors.New("无效语义版本")
	}
	for pos := range result.core {
		number, e := strconv.Atoi(parts[pos+1])
		if e != nil {
			return result, e
		}
		result.core[pos] = number
	}
	if parts[4] != "" {
		result.pre = strings.Split(parts[4], ".")
		for _, part := range result.pre {
			if numericPart(part) && len(part) > 1 && part[0] == '0' {
				return result, errors.New("预发布数字不能以 0 开头")
			}
		}
	}
	return result, nil
}
func numericPart(value string) bool {
	for _, r := range value {
		if r < '0' || r > '9' {
			return false
		}
	}
	return value != ""
}
func versionAtLeast(current, minimum string) (bool, error) {
	a, e := parseVersion(current)
	if e != nil {
		return false, e
	}
	b, e := parseVersion(minimum)
	if e != nil {
		return false, e
	}
	for pos := range a.core {
		if a.core[pos] != b.core[pos] {
			return a.core[pos] > b.core[pos], nil
		}
	}
	if len(a.pre) == 0 {
		return true, nil
	}
	if len(b.pre) == 0 {
		return false, nil
	}
	for pos := 0; pos < len(a.pre) && pos < len(b.pre); pos++ {
		x, y := a.pre[pos], b.pre[pos]
		if x == y {
			continue
		}
		nx, ny := numericPart(x), numericPart(y)
		if nx && ny {
			if len(x) != len(y) {
				return len(x) > len(y), nil
			}
			return x > y, nil
		}
		if nx != ny {
			return !nx, nil
		}
		return x > y, nil
	}
	return len(a.pre) >= len(b.pre), nil
}
