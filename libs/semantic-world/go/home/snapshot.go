package home

import (
	"bytes"
	"encoding/gob"
	"fmt"

	sw "github.com/metis-lang-dev/metis-worlds/libs/semantic-world/go/semworld"
)

// A snapshot is the world's state after a fold: the blackboard's entries, the where document, the
// surprises and the time, the board's dynamic state, and the adapter's own (the commands awaiting
// read-back, the radars, the outside readings, the fans). What New and the members' Join build
// (the map, the handlers, the ports) is not in it: a restore is New, the same joins, then
// Restore. gob, not JSON: a Gaussian not yet known holds NaN.

type snapshot struct {
	Entries   map[string]*sw.Entry
	Where     *sw.Doc
	Surprises []sw.Surprise
	Now       float64
	Taste     *sw.Taste
	Board     sw.BoardSnap
	Pend      map[string]pendSnap
	Radar     map[string]radarSnap
	Out       map[string][2]float64
	RunFrom   map[string]float64
	FeedUp    bool
	Last      float64
	Started   bool
	Fans      map[string][2]string
	Hash      string
}

type pendSnap struct {
	Value    string
	Deadline float64
	Held     string
}

type radarSnap struct {
	On    bool
	Since float64
}

// Snapshot is the world's state, to Restore later into a world built the same way.
func (h *Home) Snapshot() ([]byte, error) {
	hash := h.Hash()
	h.W.Lock()
	defer h.W.Unlock()
	s := snapshot{Entries: h.W.Entries, Where: h.W.Where, Surprises: h.W.Surprises, Now: h.W.Now, Taste: h.W.Taste, Board: h.B.Snap(),
		Pend: map[string]pendSnap{}, Radar: map[string]radarSnap{}, Out: map[string][2]float64{},
		RunFrom: h.runFrom, FeedUp: h.feedUp, Last: h.last, Started: h.started, Fans: h.fans, Hash: hash}
	for k, p := range h.pend {
		s.Pend[k] = pendSnap{p.value, p.deadline, p.held}
	}
	for k, r := range h.radar {
		s.Radar[k] = radarSnap{r.on, r.since}
	}
	for k, o := range h.out {
		if o != nil {
			s.Out[k] = *o
		}
	}
	var b bytes.Buffer
	if err := gob.NewEncoder(&b).Encode(s); err != nil {
		return nil, err
	}
	return b.Bytes(), nil
}

// Restore puts a snapshot's state into h (New on the same map and parameters, the same members
// joined); the world's hash after it must be the snapshot's, or nothing is kept.
func (h *Home) Restore(b []byte) error {
	var s snapshot
	if err := gob.NewDecoder(bytes.NewReader(b)).Decode(&s); err != nil {
		return err
	}
	// gob drops empty maps: a writer must find them made
	for _, e := range s.Entries {
		if e.Vars == nil {
			e.Vars = map[string]*sw.Var{}
		}
		for _, v := range e.Vars {
			if v.Kind == sw.VCat && v.Cat == nil {
				v.Cat = sw.Belief{}
			}
		}
	}
	if s.Where == nil {
		s.Where = sw.NewDoc()
	}
	d := s.Where
	if d.Places == nil {
		d.Places = map[string]map[string]any{}
	}
	for k, p := range d.Places {
		if p == nil {
			d.Places[k] = map[string]any{}
		}
	}
	if d.Things == nil {
		d.Things = map[string]*sw.Thing{}
	}
	if d.Belief == nil {
		d.Belief = map[string]sw.Belief{}
	}
	if d.Exists == nil {
		d.Exists = map[string]float64{}
	}
	if d.Looked == nil {
		d.Looked = map[string][]string{}
	}
	if d.Binding == nil {
		d.Binding = map[string]string{}
	}
	if s.Taste == nil {
		s.Taste = sw.NewTaste()
	}
	t := s.Taste // gob drops empty maps
	if t.Items == nil {
		t.Items = map[string]*sw.Item{}
	}
	if t.Prefs == nil {
		t.Prefs = map[string]*sw.Pref{}
	}
	if t.Priors == nil {
		t.Priors = map[string]float64{}
	}
	h.W.Lock()
	oldE, oldW, oldS, oldN, oldT := h.W.Entries, h.W.Where, h.W.Surprises, h.W.Now, h.W.Taste
	h.W.Entries, h.W.Where, h.W.Surprises, h.W.Now, h.W.Taste = s.Entries, d, s.Surprises, s.Now, t
	h.W.Unlock()
	oldB := h.B.Snap()
	h.B.SetSnap(s.Board)
	oldP, oldR, oldO, oldRF, oldF := h.pend, h.radar, h.out, h.runFrom, h.fans
	oldFU, oldL, oldSt := h.feedUp, h.last, h.started
	h.pend, h.radar, h.out = map[string]*pending{}, map[string]*radar{}, map[string]*[2]float64{}
	for k, p := range s.Pend {
		h.pend[k] = &pending{p.Value, p.Deadline, p.Held}
	}
	for k, r := range s.Radar {
		h.radar[k] = &radar{r.On, r.Since}
	}
	for k, o := range s.Out {
		o := o
		h.out[k] = &o
	}
	h.runFrom, h.fans, h.feedUp, h.last, h.started = s.RunFrom, s.Fans, s.FeedUp, s.Last, s.Started
	if h.runFrom == nil {
		h.runFrom = map[string]float64{}
	}
	if h.fans == nil {
		h.fans = map[string][2]string{}
	}
	if got := h.Hash(); got != s.Hash {
		h.W.Lock()
		h.W.Entries, h.W.Where, h.W.Surprises, h.W.Now, h.W.Taste = oldE, oldW, oldS, oldN, oldT
		h.W.Unlock()
		h.B.SetSnap(oldB)
		h.pend, h.radar, h.out, h.runFrom, h.fans = oldP, oldR, oldO, oldRF, oldF
		h.feedUp, h.last, h.started = oldFU, oldL, oldSt
		return fmt.Errorf("the restored world's hash is %s, the snapshot's %s", got, s.Hash)
	}
	return nil
}

// RestoreTaste takes only the taste from a snapshot: the person's preferences and the character's
// priors depend on no map and no member, so a world built otherwise (another map, other members)
// keeps them when the rest of the snapshot cannot be restored.
func (h *Home) RestoreTaste(b []byte) error {
	var s snapshot
	if err := gob.NewDecoder(bytes.NewReader(b)).Decode(&s); err != nil {
		return err
	}
	if s.Taste == nil {
		return nil
	}
	t := s.Taste
	if t.Items == nil {
		t.Items = map[string]*sw.Item{}
	}
	if t.Prefs == nil {
		t.Prefs = map[string]*sw.Pref{}
	}
	if t.Priors == nil {
		t.Priors = map[string]float64{}
	}
	h.W.Lock()
	h.W.Taste = t
	h.W.Unlock()
	return nil
}
