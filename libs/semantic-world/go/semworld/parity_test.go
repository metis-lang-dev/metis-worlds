package semworld

import (
	"encoding/json"
	"math"
	"os"
	"reflect"
	"testing"
)

// The Go port replays testdata/bayes_cases.json (written by the Python reference, gen_bayes_cases.py)
// step by step: the same return, the same beliefs, exists, looked and gone.

var graph = map[string][]string{"a": {"b"}, "b": {"a", "c"}, "c": {"b", "d"}, "d": {"c"}, "e": {}}

type pcase struct {
	Name   string   `json:"name"`
	Places []string `json:"places"`
	Things []string `json:"things"`
	Steps  []struct {
		Op struct {
			Op     string                     `json:"op"`
			Thing  string                     `json:"thing"`
			Place  *string                    `json:"place"`
			SeenAt map[string]string          `json:"seen_at"`
			Belief Belief                     `json:"belief"`
			Dt     float64                    `json:"dt"`
			Models map[string]json.RawMessage `json:"models"`
			Alive  []float64                  `json:"alive"`
		} `json:"op"`
		Ret json.RawMessage `json:"ret"`
		Doc struct {
			Belief map[string]Belief   `json:"belief"`
			Exists map[string]float64  `json:"exists"`
			Looked map[string][]string `json:"looked"`
			Gone   []string            `json:"gone"`
		} `json:"doc"`
	} `json:"steps"`
}

func modelOf(t *testing.T, raw json.RawMessage) Model {
	var s string
	if json.Unmarshal(raw, &s) == nil && s == "still" {
		return Still
	}
	var w struct {
		Walk struct {
			Stay, Bias, Speed float64
			Target            *string
		}
	}
	if err := json.Unmarshal(raw, &w); err != nil {
		t.Fatal(err)
	}
	nb := func(p string) []string { return graph[p] }
	var toward func(string) float64
	if w.Walk.Target != nil {
		dist := Distances(nb, *w.Walk.Target, 1e9)
		toward = func(n string) float64 {
			if d, ok := dist[n]; ok {
				return d
			}
			return 1e9
		}
	}
	return Walk(nb, toward, w.Walk.Stay, w.Walk.Bias, w.Walk.Speed, 1e-4)
}

func near(a, b map[string]Belief) bool {
	if len(a) != len(b) {
		return false
	}
	for t, ba := range a {
		bb, ok := b[t]
		if !ok || len(ba) != len(bb) {
			return false
		}
		for p, x := range ba {
			if y, ok := bb[p]; !ok || math.Abs(x-y) > 1e-12 {
				return false
			}
		}
	}
	return true
}

func TestParityWithPythonBayes(t *testing.T) {
	raw, err := os.ReadFile("../testdata/bayes_cases.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []pcase
	if err := json.Unmarshal(raw, &cases); err != nil {
		t.Fatal(err)
	}
	for _, c := range cases {
		d := NewDoc(c.Places...)
		for _, th := range c.Things {
			d.Things[th] = &Thing{}
		}
		for i, s := range c.Steps {
			var got any
			switch s.Op.Op {
			case "seen":
				p := ""
				if s.Op.Place != nil {
					p = *s.Op.Place
				}
				got = d.Seen(s.Op.Thing, p)
			case "missed":
				out := d.Missed(*s.Op.Place, s.Op.SeenAt, d.Uniform)
				if out == nil {
					out = []string{}
				}
				got = out
			case "predict":
				ms := map[string]Model{}
				for th, m := range s.Op.Models {
					ms[th] = modelOf(t, m)
				}
				var al *Alive
				if len(s.Op.Alive) == 2 {
					al = &Alive{s.Op.Alive[0], s.Op.Alive[1]}
				}
				got = d.Predict(s.Op.Dt, ms, al)
			case "set":
				d.Belief[s.Op.Thing] = copyBelief(s.Op.Belief)
				got = true
			}
			want := reflect.New(reflect.TypeOf(got)).Interface()
			if err := json.Unmarshal(s.Ret, want); err != nil {
				t.Fatalf("%s step %d: ret %s: %v", c.Name, i, s.Ret, err)
			}
			if !reflect.DeepEqual(reflect.ValueOf(want).Elem().Interface(), got) {
				t.Errorf("%s step %d %s: ret %v, python %s", c.Name, i, s.Op.Op, got, s.Ret)
			}
			if !near(d.Belief, s.Doc.Belief) {
				t.Errorf("%s step %d %s: belief\n go %v\n py %v", c.Name, i, s.Op.Op, d.Belief, s.Doc.Belief)
			}
			if !reflect.DeepEqual(d.Exists, s.Doc.Exists) && !(len(d.Exists) == 0 && len(s.Doc.Exists) == 0) {
				t.Errorf("%s step %d: exists go %v py %v", c.Name, i, d.Exists, s.Doc.Exists)
			}
			lk := s.Doc.Looked
			if lk == nil {
				lk = map[string][]string{}
			}
			if !reflect.DeepEqual(d.Looked, lk) {
				t.Errorf("%s step %d: looked go %v py %v", c.Name, i, d.Looked, lk)
			}
			if !reflect.DeepEqual(d.Gone, s.Doc.Gone) {
				t.Errorf("%s step %d: gone go %v py %v", c.Name, i, d.Gone, s.Doc.Gone)
			}
		}
	}
}
