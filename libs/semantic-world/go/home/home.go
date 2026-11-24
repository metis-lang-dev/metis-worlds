// Package home is the semantic world's first adapter: the flat (metis-worlds/home world/home.map.json)
// as entries whose variables are beliefs, written by Home Assistant's states (Ingest), the host's
// commands (Command), a person's word and Metis (semworld), read by Metis through the ports it offers
// (present, on, preset, cold, warm, humid, out_cold, someone_home, day) and by the LLM through the
// projection (Lines). State() is the same world as metis-home's HomeState families read it.
package home

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"sort"
	"strings"

	sw "github.com/metis-lang-dev/metis-worlds/libs/semantic-world/go/semworld"
)

// Map is home.map.json.
type Map struct {
	Rooms map[string]struct {
		Name  string
		Words []string
	} `json:"rooms"`
	Lights map[string]struct {
		Room   string   `json:"room"`
		Words  []string `json:"words"`
		Entity *string  `json:"entity"`
	} `json:"lights"`
	Units map[string]struct {
		Room   string   `json:"room"`
		Words  []string `json:"words"`
		Prefix string   `json:"prefix"`
	} `json:"units"`
	TVs map[string]struct {
		Room   string   `json:"room"`
		Words  []string `json:"words"`
		Entity *string  `json:"entity"`
	} `json:"tvs"`
	Radar        map[string]json.RawMessage `json:"radar"`        // room → binary_sensor | null
	Thermometers map[string]json.RawMessage `json:"thermometers"` // room → {temperature, humidity} | null
	Sun          string                     `json:"sun"`
	Thresholds   map[string]json.RawMessage `json:"thresholds"`
}

// LoadMap reads home.map.json.
func LoadMap(path string) (*Map, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	m := &Map{}
	if err := json.Unmarshal(b, m); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	return m, nil
}

func (m *Map) th(name string, def float64) float64 {
	var v []float64
	if json.Unmarshal(m.Thresholds[name], &v) == nil && len(v) > 0 {
		return v[0]
	}
	return def
}

// Params are the sensor models.
type Params struct {
	R        float64 // HA's reliability on a device state
	Mix      float64 // a device's transition between readings (the weight of "anything may have happened")
	Grace    float64 // s a commanded device is given to obey before its reading counts
	Half     float64 // s: the half-life of a device's belief while nothing can be read (unavailable, feed down)
	OnLogit  float64 // the log-odds a radar "on" sets presence to (it does not see absence that well)
	Vacate   float64 // s of radar "off" for presence to fall from sure to vacant_after's 0.3
	TempR    float64 // a thermometer's noise variance (°C²)
	TempQ    float64 // a room's temperature wander (°C² / s)
	OutQ     float64 // the outside temperature's wander (°C² / s)
	Gate     float64 // a reading beyond Gate sd is an outlier
	Warmup   float64 // s a Prana unit must run before its outside sensor reads the weather
	Untrack  float64 // sd (°C, %) beyond which a temperature is not known
	RhR, RhQ float64
}

// DefaultParams are the deployment's.
var DefaultParams = Params{R: 0.98, Mix: 0.5, Grace: 15, Half: 1800, OnLogit: sw.LMax, Vacate: 600,
	TempR: 0.09, TempQ: 0.0005, OutQ: 0.002, Gate: 4, Warmup: 120, Untrack: 1.5, RhR: 4, RhQ: 0.01}

// HAState is a Home Assistant state object (REST /api/states, the websocket's new_state).
type HAState struct {
	EntityID   string         `json:"entity_id"`
	State      string         `json:"state"`
	Attributes map[string]any `json:"attributes"`
}

type pending struct {
	value    string
	deadline float64
	held     string // the last reading while waiting ("" none)
}

type radar struct {
	on    bool
	since float64
}

// Home is the adapter.
type Home struct {
	M  *Map
	W  *sw.World
	B  *sw.Board
	P  Params
	by map[string][]func(st *HAState, now float64) // entity → handlers

	pend    map[string]*pending // var key → a command awaiting read-back
	fans    map[string][2]string
	radar   map[string]*radar
	out     map[string]*[2]float64 // unit → the last outside reading not yet folded in, and when
	runFrom map[string]float64     // unit → since when it is surely running
	feedUp  bool
	last    float64
	started bool
	therm   map[string][2]string // room → temperature, humidity entities
}

var onoff = []string{"on", "off"}

// New builds the world for M.
func New(m *Map, p Params) *Home {
	h := &Home{M: m, W: sw.New(), P: p, by: map[string][]func(*HAState, float64){},
		pend: map[string]*pending{}, fans: map[string][2]string{}, radar: map[string]*radar{},
		out: map[string]*[2]float64{}, runFrom: map[string]float64{}, therm: map[string][2]string{}}
	h.B = sw.NewBoard(h.W)
	w := h.W
	w.Add(&sw.Entry{ID: "home", Kind: sw.KPlace, Name: "the home"})
	w.Declare("home", "sun", sw.VCat, []string{"up", "down"}, nil)
	if m.Sun != "" {
		h.on(m.Sun, func(st *HAState, now float64) {
			v := "up"
			if st.State == "below_horizon" {
				v = "down"
			}
			w.ObserveCat("home", "sun", v, 0.999, 0, src(st), now)
		})
	}
	for _, r := range keys(m.Rooms) {
		w.Add(&sw.Entry{ID: r, Kind: sw.KPlace, Name: m.Rooms[r].Name, In: "home"})
		w.Declare(r, "presence", sw.VOdds, nil, nil)
		w.Declare(r, "temperature", sw.VGauss, nil, nil)
		w.Declare(r, "humidity", sw.VGauss, nil, nil)
		var e string
		if json.Unmarshal(m.Radar[r], &e) == nil && e != "" {
			h.Entries(r)["radar"] = e
			room := r
			h.on(e, func(st *HAState, now float64) { h.radarReading(room, st, now) })
		}
		var t struct{ Temperature, Humidity string }
		if json.Unmarshal(m.Thermometers[r], &t) == nil && t.Temperature != "" {
			h.therm[r] = [2]string{t.Temperature, t.Humidity}
			room := r
			h.on(t.Temperature, func(st *HAState, now float64) { h.gauss(room, "temperature", st, p.TempR, now) })
			if t.Humidity != "" {
				h.on(t.Humidity, func(st *HAState, now float64) { h.gauss(room, "humidity", st, p.RhR, now) })
			}
		}
	}
	for _, l := range keys(m.Lights) {
		d := m.Lights[l]
		h.device(l, m.Rooms[d.Room].Name+" light", d.Room, d.Entity, "light")
	}
	for _, t := range keys(m.TVs) {
		d := m.TVs[t]
		h.device(t, "the TV", d.Room, d.Entity, "tv")
	}
	for _, u := range keys(m.Units) {
		d := m.Units[u]
		w.Add(&sw.Entry{ID: u, Kind: sw.KDevice, Name: m.Rooms[d.Room].Name + " ventilation", In: d.Room,
			Attrs: map[string]string{"prefix": d.Prefix, "class": "unit"}})
		w.Declare(u, "power", sw.VCat, onoff, nil)
		w.Declare(u, "preset", sw.VCat, []string{"normal", "night", "boost"}, nil)
		w.Declare(u, "heater", sw.VCat, onoff, nil)
		w.Declare(u, "winter", sw.VCat, onoff, nil)
		w.Declare(u, "reach", sw.VOdds, nil, nil)
		w.Declare(u, "outside", sw.VGauss, nil, nil)
		unit, pre := u, d.Prefix
		for i, f := range []string{"supply", "extract"} {
			i := i
			h.on(fmt.Sprintf("fan.%s_%s_fan", pre, f), func(st *HAState, now float64) { h.fan(unit, i, st, now) })
		}
		for _, sv := range []string{"heater", "winter"} {
			sv := sv
			h.on(fmt.Sprintf("switch.%s_%s", pre, sv), func(st *HAState, now float64) {
				if !bad(st) {
					h.reading(unit, sv, st.State, src(st), now)
				}
			})
		}
		h.on(fmt.Sprintf("sensor.%s_outside_temperature", pre), func(st *HAState, now float64) {
			if z, ok := num(st); ok {
				h.out[unit] = &[2]float64{z, now}
			}
		})
	}
	h.ports()
	return h
}

// Entries are an entry's attributes (the entity ids it is read from).
func (h *Home) Entries(id string) map[string]string {
	e := h.W.Entries[id]
	if e.Attrs == nil {
		e.Attrs = map[string]string{}
	}
	return e.Attrs
}

func (h *Home) device(id, name, room string, entity *string, class string) {
	h.W.Add(&sw.Entry{ID: id, Kind: sw.KDevice, Name: name, In: room, Attrs: map[string]string{"class": class}})
	h.W.Declare(id, "power", sw.VCat, onoff, nil)
	h.W.Declare(id, "reach", sw.VOdds, nil, nil)
	if entity == nil || *entity == "" {
		h.W.Entries[id].Attrs["absent"] = "not in Home Assistant yet"
		return
	}
	h.W.Entries[id].Attrs["entity"] = *entity
	dev := id
	h.on(*entity, func(st *HAState, now float64) {
		if h.reach(dev, st, now) {
			v := "on"
			if st.State == "off" || st.State == "standby" {
				v = "off"
			}
			h.reading(dev, "power", v, src(st), now)
		}
	})
}

func (h *Home) on(entity string, f func(*HAState, float64)) { h.by[entity] = append(h.by[entity], f) }

func src(st *HAState) sw.Source { return sw.Source{Kind: "sensor", Who: st.EntityID} }

func bad(st *HAState) bool {
	return st == nil || st.State == "unavailable" || st.State == "unknown" || st.State == ""
}

func num(st *HAState) (float64, bool) {
	if bad(st) {
		return 0, false
	}
	var z float64
	_, err := fmt.Sscan(st.State, &z)
	return z, err == nil
}

// reach: a device's reading says it answers (or not). → whether its state can be read.
func (h *Home) reach(id string, st *HAState, now float64) bool {
	if bad(st) {
		h.W.ObserveOdds(id, "reach", -2*sw.LMax, src(st), now)
		for _, v := range h.W.Entries[id].Vars {
			v.Unsure = true
		}
		return false
	}
	h.W.ObserveOdds(id, "reach", 2*sw.LMax, src(st), now)
	return true
}

// reading folds a device state in, through a pending command's grace.
func (h *Home) reading(id, name, value string, s sw.Source, now float64) {
	k := sw.Key(id, name)
	if pd := h.pend[k]; pd != nil {
		if value == pd.value { // obeyed: the command confirmed
			delete(h.pend, k)
		} else if now < pd.deadline { // still obeying: held, not folded
			pd.held = value
			return
		} else {
			h.W.Surprised("probabilistic", k, fmt.Sprintf("commanded %s, reads %s after %.0f s", pd.value, value, h.P.Grace), now)
			delete(h.pend, k)
		}
	}
	h.W.ObserveCat(id, name, value, h.P.R, h.P.Mix, s, now)
}

func (h *Home) fan(unit string, i int, st *HAState, now float64) {
	if !h.reach(unit, st, now) {
		return
	}
	f := h.fans[unit]
	f[i] = st.State
	h.fans[unit] = f
	v := "off"
	if f[0] == "on" || f[1] == "on" {
		v = "on"
	}
	h.reading(unit, "power", v, src(st), now)
	if i == 0 && st.State == "on" {
		if pm, _ := st.Attributes["preset_mode"].(string); pm != "" {
			h.reading(unit, "preset", pm, src(st), now)
		} else {
			h.reading(unit, "preset", "normal", src(st), now)
		}
	}
}

func (h *Home) radarReading(room string, st *HAState, now float64) {
	if bad(st) {
		delete(h.radar, room)
		h.W.Var(room, "presence").Unsure = true
		return
	}
	on := st.State == "on"
	if r := h.radar[room]; r != nil && r.on == on {
		return
	}
	h.radar[room] = &radar{on: on, since: now}
	if on { // a radar that sees someone is believed at once
		v := h.W.Var(room, "presence")
		h.W.ObserveOdds(room, "presence", h.P.OnLogit-v.Odds, src(st), now)
	}
}

func (h *Home) gauss(room, name string, st *HAState, r float64, now float64) {
	if z, ok := num(st); ok {
		if !h.W.ObserveGauss(room, name, z, r, h.P.Gate, src(st), now) {
			h.W.Surprised("probabilistic", sw.Key(room, name), fmt.Sprintf("an outlier reading %.1f refused", z), now)
		}
	}
}

// Ingest folds one Home Assistant state in (the initial get_states, then every state_changed).
func (h *Home) Ingest(st HAState, now float64) {
	h.W.Lock()
	defer h.W.Unlock()
	h.feedUp = true
	for _, f := range h.by[st.EntityID] {
		f(&st, now)
	}
}

// FeedDown: Home Assistant is unreachable; nothing can be read until the next Ingest.
func (h *Home) FeedDown(now float64) {
	h.W.Lock()
	defer h.W.Unlock()
	h.feedUp = false
	for _, e := range h.W.Entries {
		for _, v := range e.Vars {
			if v.Src.Kind == "sensor" {
				v.Unsure = true
			}
		}
	}
}

// Command is the host's own command (metis-home's Do, a tool call): its prediction written at once
// (p 0.9, source command), read back after Grace.
func (h *Home) Command(id, name, value string, now float64) error {
	h.W.Lock()
	defer h.W.Unlock()
	v := h.W.Var(id, name)
	if v == nil || v.Kind != sw.VCat {
		return fmt.Errorf("home: no device variable %s", sw.Key(id, name))
	}
	bel := sw.Likelihood(v.Values, value, 0.9)
	h.W.SetCat(id, name, bel, sw.Source{Kind: "command", Who: "metis-home"}, now)
	h.pend[sw.Key(id, name)] = &pending{value: value, deadline: now + h.P.Grace}
	return nil
}

// Settle is the boundary step at NOW: the time models (presence decay, temperature wander, the stale
// forgetting), the commands past their grace, the outside readings the units may take, then the
// board's counters.
func (h *Home) Settle(now float64) {
	h.W.Lock()
	defer h.W.Unlock()
	dt := now - h.last
	if !h.started {
		dt, h.started = 0, true
	}
	h.last = now
	h.W.Now = now
	if dt > 0 {
		h.tick(dt, now)
	}
	h.B.Settle()
}

func (h *Home) tick(dt, now float64) {
	w := h.W
	vac := h.M.th("vacant_after_s", h.P.Vacate)
	rate := (h.P.OnLogit - sw.LogOdds(0.3)) / vac // sure → 0.3 over vacant_after
	for _, r := range keys(h.M.Rooms) {
		if rd := h.radar[r]; rd != nil && !rd.on && h.feedUp { // the radar's "nobody", while it can be heard
			w.ObserveOdds(r, "presence", -rate*dt, sw.Source{Kind: "sensor", Who: "radar"}, now)
		}
		for _, n := range []string{"temperature", "humidity"} {
			v := w.Var(r, n)
			q := h.P.TempQ
			if n == "humidity" {
				q = h.P.RhQ
			}
			v.G.Predict(dt, q)
		}
	}
	for _, id := range sortedEntries(w) {
		e := w.Entries[id]
		if e.Kind != sw.KDevice {
			continue
		}
		for _, n := range []string{"power", "preset", "heater", "winter"} {
			v := e.Vars[n]
			if v == nil {
				continue
			}
			if v.Unsure || !h.feedUp {
				w.Relax(id, n, dt, h.P.Half)
			}
		}
	}
	for _, k := range keys(h.pend) { // past grace: what was held is read now (sorted: surprises replay in order)
		pd := h.pend[k]
		if now < pd.deadline {
			continue
		}
		id, n, _ := strings.Cut(k, ".")
		if pd.held != "" && pd.held != pd.value {
			w.Surprised("probabilistic", k, fmt.Sprintf("commanded %s, reads %s after %.0f s", pd.value, pd.held, h.P.Grace), now)
			w.ObserveCat(id, n, pd.held, h.P.R, h.P.Mix, sw.Source{Kind: "sensor", Who: k}, now)
		} else if pd.held == "" {
			w.Surprised("probabilistic", k, fmt.Sprintf("commanded %s, no reading after %.0f s", pd.value, h.P.Grace), now)
			w.Var(id, n).Unsure = true
		}
		delete(h.pend, k)
	}
	for _, u := range keys(h.M.Units) {
		run := w.Var(u, "power").P("on") >= 0.9 && w.Var(u, "power").Src.Kind == "sensor"
		if !run {
			delete(h.runFrom, u)
		} else if _, ok := h.runFrom[u]; !ok {
			h.runFrom[u] = w.Var(u, "power").At // since the reading that said it runs
		}
		v := w.Var(u, "outside")
		v.G.Predict(dt, h.P.OutQ)
		t, ok := h.runFrom[u]
		if !ok || now-t < h.P.Warmup { // the sensor sits in the unit: stopped, it reads the unit
			v.Unsure = true
			continue
		}
		if z := h.out[u]; z != nil && z[1] >= t+h.P.Warmup { // a reading from inside the warm-up is the unit's
			h.W.ObserveGauss(u, "outside", z[0], 0.25, h.P.Gate, sw.Source{Kind: "sensor", Who: "sensor." + w.Entries[u].Attrs["prefix"] + "_outside_temperature"}, now)
			h.out[u] = nil
		} else if z != nil && z[1] < t+h.P.Warmup {
			h.out[u] = nil
		}
	}
}

func sortedEntries(w *sw.World) []string {
	out := make([]string, 0, len(w.Entries))
	for k := range w.Entries {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

func keys[V any](m map[string]V) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		if !strings.HasPrefix(k, "_") {
			out = append(out, k)
		}
	}
	sort.Strings(out)
	return out
}

// ── the ports Metis reads (spec 16): names a home manifest's beliefs:/levels: may use ──

func (h *Home) gaussKnown(id, name string) (*sw.Var, bool) {
	v := h.W.Var(id, name)
	return v, v != nil && v.G.Known && v.G.Sd() <= h.P.Untrack
}

func (h *Home) ports() {
	w, m := h.W, h.M
	one := func(ids []string) func() [][]string {
		return func() [][]string {
			out := make([][]string, len(ids))
			for i, id := range ids {
				out[i] = []string{id}
			}
			return out
		}
	}
	srcOf := func(name string) func([]string) sw.Source {
		return func(a []string) sw.Source {
			if v := w.Var(a[0], name); v != nil {
				return v.Src
			}
			return sw.Source{}
		}
	}
	var sensed []string
	for _, r := range keys(m.Rooms) {
		if h.W.Entries[r].Attrs["radar"] != "" {
			sensed = append(sensed, r)
		}
	}
	h.B.Offer(&sw.Port{Name: "present", Keys: one(sensed), Src: srcOf("presence"), P: func(a []string) (float64, bool) {
		v := w.Var(a[0], "presence")
		return sw.P(v.Odds), v.Src.Kind != "prior"
	}})
	h.B.Offer(&sw.Port{Name: "someone_home", Keys: func() [][]string {
		if len(sensed) == 0 {
			return nil
		}
		return [][]string{{}}
	}, P: func([]string) (float64, bool) {
		none := 1.0
		for _, r := range sensed {
			none *= 1 - sw.P(w.Var(r, "presence").Odds)
		}
		return 1 - none, true
	}})
	var devs []string
	for _, id := range sortedEntries(w) {
		if e := w.Entries[id]; e.Kind == sw.KDevice && e.Attrs["absent"] == "" {
			devs = append(devs, id)
		}
	}
	h.B.Offer(&sw.Port{Name: "on", Keys: one(devs), Src: srcOf("power"), P: func(a []string) (float64, bool) {
		v := w.Var(a[0], "power")
		return v.P("on"), v.Src.Kind != "prior"
	}})
	// a device's power per kind (unit_on, light_on, tv_on): a package's level over one kind reads only
	// that kind's keys, so a light's power never reaches a package whose level pred takes units
	for _, kind := range []string{"unit", "light", "tv"} {
		var ks []string
		for _, id := range devs {
			if w.Entries[id].Attrs["class"] == kind {
				ks = append(ks, id)
			}
		}
		h.B.Offer(&sw.Port{Name: kind + "_on", Keys: one(ks), Src: srcOf("power"), P: func(a []string) (float64, bool) {
			v := w.Var(a[0], "power")
			return v.P("on"), v.Src.Kind != "prior"
		}})
	}
	h.B.Offer(&sw.Port{Name: "reachable", Keys: one(devs), Src: srcOf("reach"), P: func(a []string) (float64, bool) {
		v := w.Var(a[0], "reach")
		return sw.P(v.Odds), v.Src.Kind != "prior"
	}})
	units := keys(m.Units)
	h.B.Offer(&sw.Port{Name: "preset", One: "M", Src: srcOf("preset"), Keys: func() [][]string {
		var out [][]string
		for _, u := range units {
			for _, p := range []string{"boost", "night", "normal"} {
				out = append(out, []string{u, p})
			}
		}
		return out
	}, P: func(a []string) (float64, bool) {
		v := w.Var(a[0], "preset")
		return v.P(a[1]), v.Src.Kind != "prior"
	}})
	rooms := keys(m.Rooms)
	below := func(name, th string, def float64, below bool) func([]string) (float64, bool) {
		return func(a []string) (float64, bool) {
			v, ok := h.gaussKnown(a[0], name)
			if !ok {
				return 0, false
			}
			p := v.G.PBelow(m.th(th, def))
			if !below {
				p = 1 - p
			}
			return p, true
		}
	}
	h.B.Offer(&sw.Port{Name: "cold", Keys: one(rooms), Src: srcOf("temperature"), P: below("temperature", "room_cold_c", 19, true)})
	h.B.Offer(&sw.Port{Name: "warm", Keys: one(rooms), Src: srcOf("temperature"), P: below("temperature", "room_warm_c", 26, false)})
	h.B.Offer(&sw.Port{Name: "humid", Keys: one(rooms), Src: srcOf("humidity"), P: func(a []string) (float64, bool) {
		v := w.Var(a[0], "humidity")
		if !v.G.Known || v.G.Sd() > 5 {
			return 0, false
		}
		return 1 - v.G.PBelow(m.th("humid_pct", 65)), true
	}})
	h.B.Offer(&sw.Port{Name: "out_cold", Keys: one(units), Src: srcOf("outside"), P: func(a []string) (float64, bool) {
		v, ok := h.gaussKnown(a[0], "outside")
		if !ok || v.Unsure && v.G.Sd() > 1 {
			return 0, false
		}
		return v.G.PBelow(m.th("outside_cold_c", 8)), true
	}})
	h.B.Offer(&sw.Port{Name: "day", Keys: func() [][]string { return [][]string{{}} }, Src: func([]string) sw.Source {
		return w.Var("home", "sun").Src
	}, P: func([]string) (float64, bool) {
		v := w.Var("home", "sun")
		return v.P("up"), v.Src.Kind != "prior"
	}})
}

// Lines are the LLM's projection now.
func (h *Home) Lines(now float64) []sw.Line {
	h.W.Lock()
	defer h.W.Unlock()
	return sw.Project(h.W, now, h.phrase)
}

var powerWords = map[string]map[string]string{
	"unit":  {"on": "running", "off": "stopped"},
	"light": {"on": "on", "off": "off"},
	"tv":    {"on": "on", "off": "off"},
}

func (h *Home) phrase(e *sw.Entry, name string, v *sw.Var) (sw.Phrase, bool) {
	switch {
	case e.ID == "home" && name == "sun":
		return sw.Phrase{Subject: "the sun", Words: map[string]string{"up": "up (day)", "down": "down (night)"}}, true
	case e.Kind == sw.KPlace && name == "presence":
		if e.Attrs["radar"] == "" {
			return sw.Phrase{}, false // unsensed: said once, by the README, not per room per turn
		}
		return sw.Phrase{Subject: "someone in the " + e.Name, Words: map[string]string{"yes": "yes", "no": "no"}}, true
	case e.Kind == sw.KPlace && (name == "temperature" || name == "humidity"):
		if _, ok := h.therm[e.ID]; !ok {
			return sw.Phrase{}, false
		}
		if name == "humidity" {
			return sw.Phrase{Subject: e.Name + " humidity", Unit: "%"}, true
		}
		return sw.Phrase{Subject: e.Name + " temperature", Unit: " °C", Digits: 1}, true
	case e.Kind == sw.KDevice:
		class := e.Attrs["class"]
		if name == "reach" {
			return sw.Phrase{}, false // said through the others' "no fresh reading possible"
		}
		if a := e.Attrs["absent"]; a != "" {
			if name == "power" {
				return sw.Phrase{Subject: e.Name, Absent: a}, true
			}
			return sw.Phrase{}, false
		}
		switch name {
		case "power":
			return sw.Phrase{Subject: e.Name, Words: powerWords[class]}, true
		case "preset":
			if v.P("on") == 0 && h.W.Var(e.ID, "power").P("on") < 0.5 {
				return sw.Phrase{}, false // a stopped unit's mode is not news
			}
			return sw.Phrase{Subject: e.Name + " mode"}, true
		case "heater", "winter":
			return sw.Phrase{Subject: e.Name + " " + name}, true
		case "outside":
			if !v.G.Known {
				return sw.Phrase{}, false
			}
			if v.Unsure && h.W.Var(e.ID, "power").P("off") > 0.5 {
				return sw.Phrase{Subject: "outside air (" + e.Name + ")", Absent: "not measured while the unit is stopped"}, true
			}
			return sw.Phrase{Subject: "outside air (" + e.Name + ")", Unit: " °C", Digits: 1}, true
		}
	}
	return sw.Phrase{}, false
}

// ── metis-home's families: the same world as its HomeState reads it ──

// Light, Unit, TV, Climate mirror metis-agent internal/host's HomeState records.
type Light struct{ Lit, OK bool }
type Unit struct {
	Running        bool
	Preset         string
	Heater, Winter bool
	OK             bool
	Outside        *float64
}
type TV struct{ On, OK bool }
type Climate struct {
	C  float64
	RH *float64
}

// State is HomeState: what the families' readings are computed from.
type State struct {
	Lights   map[string]Light
	Units    map[string]Unit
	TVs      map[string]TV
	IRReady  bool
	Presence map[string]string // "" unsensed | occupied | empty
	Climate  map[string]*Climate
	SunUp    bool
}

// State is the world's likeliest reading in HomeState's terms. A device is ok when it is in Home
// Assistant, reachable and read; presence is occupied at p ≥ 0.5 (the vacant timer stays the host's).
func (h *Home) State() State {
	h.W.Lock()
	defer h.W.Unlock()
	w := h.W
	s := State{Lights: map[string]Light{}, Units: map[string]Unit{}, TVs: map[string]TV{},
		Presence: map[string]string{}, Climate: map[string]*Climate{}}
	ok := func(id string) bool {
		e := w.Entries[id]
		r := w.Var(id, "reach")
		return e.Attrs["absent"] == "" && r.Src.Kind != "prior" && sw.P(r.Odds) >= 0.5 && h.feedUp
	}
	for _, l := range keys(h.M.Lights) {
		s.Lights[l] = Light{Lit: w.Var(l, "power").P("on") > 0.5, OK: ok(l)}
	}
	for _, t := range keys(h.M.TVs) {
		s.TVs[t] = TV{On: w.Var(t, "power").P("on") > 0.5, OK: ok(t)}
	}
	for _, u := range keys(h.M.Units) {
		pr, _ := w.Var(u, "preset").Top()
		un := Unit{Running: w.Var(u, "power").P("on") > 0.5, Preset: pr, OK: ok(u),
			Heater: w.Var(u, "heater").P("on") > 0.5, Winter: w.Var(u, "winter").P("on") > 0.5}
		if v, known := h.gaussKnown(u, "outside"); known && !v.Unsure {
			x := math.Round(v.G.Mean*10) / 10
			un.Outside = &x
		}
		s.Units[u] = un
	}
	for _, r := range keys(h.M.Rooms) {
		if w.Entries[r].Attrs["radar"] != "" && h.radar[r] != nil {
			s.Presence[r] = "empty"
			if sw.P(w.Var(r, "presence").Odds) >= 0.5 {
				s.Presence[r] = "occupied"
			}
		} else {
			s.Presence[r] = ""
		}
		if v, known := h.gaussKnown(r, "temperature"); known {
			c := &Climate{C: math.Round(v.G.Mean*10) / 10}
			if hv := w.Var(r, "humidity"); hv.G.Known {
				x := math.Round(hv.G.Mean)
				c.RH = &x
			}
			s.Climate[r] = c
		}
	}
	s.SunUp = w.Var("home", "sun").P("down") < 0.5
	return s
}
