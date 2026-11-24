package home

import (
	"bufio"
	"encoding/json"
	"os"
	"reflect"
	"strings"
	"testing"

	sw "github.com/metis-lang-dev/metis-worlds/libs/semantic-world/go/semworld"
)

// dayEvents reads testdata/home.replay.jsonl (the replay tool's steps) as events.
func dayEvents(t *testing.T) []Event {
	f, err := os.Open("../testdata/home.replay.jsonl")
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	var evs []Event
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		var s struct {
			T        float64  `json:"t"`
			HA       *HAState `json:"ha"`
			Command  *struct{ ID, Var, Value string }
			Report   *struct{ Who, ID, Var, Value, Ref string }
			Conclude *struct {
				Member, Fact, Rule string
				On                 bool
			}
			Feed   string `json:"feed"`
			Settle bool   `json:"settle"`
			Note   string `json:"note"`
		}
		if err := json.Unmarshal([]byte(line), &s); err != nil {
			t.Fatal(err)
		}
		switch {
		case s.HA != nil:
			evs = append(evs, Event{At: s.T, Kind: "ha_state", HA: s.HA})
		case s.Command != nil:
			evs = append(evs, Event{At: s.T, Kind: "command", ID: s.Command.ID, Var: s.Command.Var, Value: s.Command.Value})
		case s.Report != nil:
			evs = append(evs, Event{At: s.T, Kind: "report", Person: s.Report.Who, ID: s.Report.ID, Var: s.Report.Var, Value: s.Report.Value, Ref: s.Report.Ref})
		case s.Conclude != nil:
			evs = append(evs, Event{At: s.T, Kind: "conclude", Member: s.Conclude.Member, Fact: s.Conclude.Fact, On: s.Conclude.On, Rule: s.Conclude.Rule})
		case s.Feed == "down":
			evs = append(evs, Event{At: s.T, Kind: "feed_down"})
		}
		if s.Settle || s.Note != "" {
			evs = append(evs, Event{At: s.T, Kind: "settle"})
		}
	}
	return evs
}

func dayHome(t *testing.T) *Home {
	m, err := LoadMap("../testdata/home.wired.map.json")
	if err != nil {
		t.Fatal(err)
	}
	h := New(m, DefaultParams)
	man, err := sw.ReadManifest("../testdata/comfort.domain.yaml", "comfort")
	if err != nil {
		t.Fatal(err)
	}
	if err := h.B.Join(man); err != nil {
		t.Fatal(err)
	}
	return h
}

type trace struct {
	Hashes []string
	Outs   []Out
}

func run(t *testing.T, evs []Event) trace {
	h := dayHome(t)
	var tr trace
	for i, ev := range evs {
		out, err := h.Apply(ev)
		if err != nil {
			t.Fatalf("event %d %+v: %v", i, ev, err)
		}
		tr.Hashes = append(tr.Hashes, h.Hash())
		tr.Outs = append(tr.Outs, out)
	}
	return tr
}

// TestReplayIsDeterministic: the world is a function of its events. The same day applied again
// gives the same checkpoint after every event and the same outputs (members' lines, beats,
// projected lines, surprises), however Go orders its maps this time.
func TestReplayIsDeterministic(t *testing.T) {
	evs := dayEvents(t)
	if len(evs) < 20 {
		t.Fatalf("the day has %d events", len(evs))
	}
	first := run(t, evs)
	sur := 0
	for _, o := range first.Outs {
		sur += len(o.Surprises)
	}
	if sur == 0 {
		t.Fatal("the day raised no surprise: the pending commands' order is not exercised")
	}
	for k := 0; k < 30; k++ {
		again := run(t, evs)
		for i := range evs {
			if again.Hashes[i] != first.Hashes[i] {
				t.Fatalf("run %d: the checkpoint after event %d (%s) differs", k, i, evs[i].Kind)
			}
			if !reflect.DeepEqual(again.Outs[i], first.Outs[i]) {
				t.Fatalf("run %d: the output of event %d (%s) differs:\n%+v\n%+v", k, i, evs[i].Kind, again.Outs[i], first.Outs[i])
			}
		}
	}
}

// TestHashFollowsTheWorld: a reading that changes a belief changes the checkpoint; the same
// world built twice hashes the same.
func TestHashFollowsTheWorld(t *testing.T) {
	a, b := dayHome(t), dayHome(t)
	if a.Hash() != b.Hash() {
		t.Fatal("two fresh worlds hash differently")
	}
	ev := Event{At: 1, Kind: "ha_state", HA: &HAState{EntityID: "fan.lab_supply_fan", State: "on"}}
	if _, err := a.Apply(ev); err != nil {
		t.Fatal(err)
	}
	if a.Hash() == b.Hash() {
		t.Fatal("a reading did not change the checkpoint")
	}
	if _, err := b.Apply(ev); err != nil {
		t.Fatal(err)
	}
	if a.Hash() != b.Hash() {
		t.Fatal("the same event, different checkpoints")
	}
	if _, err := a.Apply(Event{At: 2, Kind: "nonsense"}); err == nil {
		t.Fatal("an unknown kind was accepted")
	}
}

// TestSurprisesInOrder: two commands past their grace in one beat raise their surprises in the
// same order every time (the pending commands are walked sorted, not in map order).
func TestSurprisesInOrder(t *testing.T) {
	evs := []Event{
		{At: 0, Kind: "settle"},
		{At: 1, Kind: "command", ID: "u2", Var: "power", Value: "on"},
		{At: 1, Kind: "command", ID: "u1", Var: "power", Value: "on"},
		{At: 1, Kind: "command", ID: "u2", Var: "heater", Value: "on"},
		{At: 1, Kind: "command", ID: "u1", Var: "winter", Value: "on"},
		{At: 1 + DefaultParams.Grace + 1, Kind: "settle"},
	}
	var first []sw.Surprise
	for k := 0; k < 40; k++ {
		tr := run(t, evs)
		got := tr.Outs[len(evs)-1].Surprises
		if len(got) != 4 {
			t.Fatalf("want 4 surprises (no read-back), got %+v", got)
		}
		if k == 0 {
			first = got
		} else if !reflect.DeepEqual(got, first) {
			t.Fatalf("run %d: surprises in another order:\n%+v\n%+v", k, got, first)
		}
	}
}
