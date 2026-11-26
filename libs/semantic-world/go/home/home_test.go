package home

import (
	"reflect"
	"strings"
	"testing"

	sw "github.com/metis-lang-dev/metis-worlds/libs/semantic-world/go/semworld"
)

func wired(t *testing.T) *Home {
	m, err := LoadMap("../testdata/home.wired.map.json")
	if err != nil {
		t.Fatal(err)
	}
	return New(m, DefaultParams)
}

func st(id, state string, attrs ...any) HAState {
	a := map[string]any{}
	for i := 0; i+1 < len(attrs); i += 2 {
		a[attrs[i].(string)] = attrs[i+1]
	}
	return HAState{EntityID: id, State: state, Attributes: a}
}

func line(h *Home, now float64, key string) string {
	for _, l := range h.Lines(now) {
		if l.Key == key {
			return l.Text
		}
	}
	return ""
}

func TestTheRealMapLoads(t *testing.T) {
	m, err := LoadMap("../testdata/home.map.json")
	if err != nil {
		t.Fatal(err)
	}
	h := New(m, DefaultParams)
	if got := line(h, 0, "l1.power"); got != "living room light: not in Home Assistant yet" {
		t.Fatalf("%q", got)
	}
	if ks := h.B.Ports(); !reflect.DeepEqual(ks, []string{"cold", "day", "humid", "light_on", "on", "out_cold", "present", "preset", "reachable", "someone_home", "strain", "tv_on", "unit_on", "warm"}) {
		t.Fatal(ks)
	}
}

func TestADeviceReadingAndItsChange(t *testing.T) {
	h := wired(t)
	h.Ingest(st("fan.lab_supply_fan", "on", "preset_mode", "night"), 1)
	h.Ingest(st("fan.lab_extract_fan", "on"), 1)
	h.Settle(1)
	if got := line(h, 1, "u2.power"); got != "lab ventilation: running (sure, sensor, just now)" {
		t.Fatalf("%q", got)
	}
	if got := line(h, 1, "u2.preset"); !strings.HasPrefix(got, "lab ventilation mode: night (sure") {
		t.Fatalf("%q", got)
	}
	h.Ingest(st("fan.lab_supply_fan", "off"), 5)
	h.Ingest(st("fan.lab_extract_fan", "off"), 5)
	if p := h.W.Var("u2", "power").P("off"); p < 0.9 {
		t.Fatalf("one reading of a switch is believed (the transition model): %v", p)
	}
}

func TestACommandIsPredictedThenReadBack(t *testing.T) {
	h := wired(t)
	h.Ingest(st("fan.lab_supply_fan", "off"), 0)
	h.Ingest(st("fan.lab_extract_fan", "off"), 0)
	h.Settle(0)
	h.Command("u2", "power", "on", 1)
	if got := line(h, 1, "u2.power"); !strings.Contains(got, "running (likely, commanded, not yet confirmed") {
		t.Fatalf("%q", got)
	}
	h.Ingest(st("fan.lab_supply_fan", "off"), 3) // HA lags: held, not folded
	if h.W.Var("u2", "power").P("on") != 0.9 {
		t.Fatal("a reading inside the grace is held")
	}
	h.Ingest(st("fan.lab_supply_fan", "on"), 4)
	if h.W.Var("u2", "power").Src.Kind != "sensor" || len(h.W.Surprises) != 0 {
		t.Fatal("obeyed: confirmed by the sensor")
	}
	// the bedroom unit does not obey
	h.Ingest(st("fan.bedroom_badriom_supply_fan", "off"), 0)
	h.Ingest(st("fan.bedroom_badriom_extract_fan", "off"), 0)
	h.Command("u1", "power", "on", 10)
	h.Ingest(st("fan.bedroom_badriom_supply_fan", "off"), 12)
	h.Settle(30)
	if len(h.W.Surprises) != 1 || h.W.Surprises[0].Key != "u1.power" || h.W.Var("u1", "power").P("off") < 0.9 {
		t.Fatalf("not obeyed: a surprise and the reading wins: %+v %v", h.W.Surprises, h.W.Var("u1", "power").Cat)
	}
}

func TestUnavailableAndFeedDownForget(t *testing.T) {
	h := wired(t)
	h.Ingest(st("light.lab", "on"), 0)
	h.Settle(0)
	h.Ingest(st("light.lab", "unavailable"), 10)
	h.Settle(10)
	h.Settle(10 + 1800)
	v := h.W.Var("l3", "power")
	if p := v.P("on"); p > 0.8 || p < 0.6 {
		t.Fatalf("half-life: halfway back to 50/50, got %v", p)
	}
	if !strings.Contains(line(h, 1810, "l3.power"), "no fresh reading possible") {
		t.Fatal(line(h, 1810, "l3.power"))
	}
	if h.State().Lights["l3"].OK {
		t.Fatal("unreachable is not ok")
	}
}

func TestPresenceDecaysToVacant(t *testing.T) {
	h := wired(t)
	h.B.Join(&sw.Manifest{Name: "lights", Levels: map[string]sw.LevelSpec{"presence": {
		From: map[string]string{"belief": "present"}, At: []float64{0.3, 0.7}, Names: []string{"vacant", "unsure", "occupied"}}}})
	h.Ingest(st("binary_sensor.lab_presence", "on"), 0)
	h.Settle(0)
	if got := h.B.Lines("lights"); !reflect.DeepEqual(got, []string{"+presence(occupied, r2) 1"}) {
		t.Fatal(got)
	}
	h.Ingest(st("binary_sensor.lab_presence", "off"), 10)
	for s := 10.0; s <= 450; s += 10 {
		h.Settle(s)
	}
	if got := h.B.Lines("lights"); !reflect.DeepEqual(got, []string{"-presence(occupied, r2) 1", "+presence(unsure, r2) 1"}) {
		t.Fatalf("seven minutes off (0.7 is crossed at ~390 s): unsure, got %v", got)
	}
	for s := 460.0; s <= 620; s += 10 {
		h.Settle(s)
	}
	if got := h.B.Lines("lights"); !reflect.DeepEqual(got, []string{"-presence(unsure, r2) 1", "+presence(vacant, r2) 1"}) {
		t.Fatalf("vacant_after: vacant, got %v", got)
	}
	if h.State().Presence["r2"] != "empty" || h.State().Presence["r1"] != "" {
		t.Fatal(h.State().Presence)
	}
}

func TestThermometerFiltersAndLevels(t *testing.T) {
	h := wired(t)
	for i, z := range []string{"18.2", "18.4", "18.3", "35.0", "18.3"} {
		h.Ingest(st("sensor.lab_temperature", z), float64(i*60))
		h.Settle(float64(i * 60))
	}
	if len(h.W.Surprises) != 1 || !strings.Contains(h.W.Surprises[0].Why, "outlier") {
		t.Fatalf("%+v", h.W.Surprises)
	}
	p, ok := h.B.Weight("cold")([]string{"r2"}, nil), true
	if !ok || p < 0.95 {
		t.Fatalf("18.3 °C ±0.1 is surely below 19: %v", p)
	}
	if h.B.Weight("cold")([]string{"r1"}, nil) != 1 {
		t.Fatal("an untracked room prices flat")
	}
	if got := line(h, 240, "r2.temperature"); !strings.HasPrefix(got, "lab temperature: 18.3 °C ±0.") {
		t.Fatal(got)
	}
	if h.State().Climate["r2"].C != 18.3 || h.State().Climate["r1"] != nil {
		t.Fatal(h.State().Climate)
	}
}

func TestPranaOutsideOnlyWhileRunning(t *testing.T) {
	h := wired(t)
	h.Ingest(st("fan.lab_supply_fan", "off"), 0)
	h.Ingest(st("fan.lab_extract_fan", "off"), 0)
	h.Ingest(st("sensor.lab_outside_temperature", "27.0"), 0) // the unit's own warmth
	h.Settle(0)
	h.Settle(300)
	if h.W.Var("u2", "outside").G.Known || h.State().Units["u2"].Outside != nil {
		t.Fatal("a stopped unit's outside reading is not the weather")
	}
	h.Ingest(st("fan.lab_supply_fan", "on"), 300)
	h.Ingest(st("sensor.lab_outside_temperature", "5.0"), 330)
	h.Settle(330)
	if h.W.Var("u2", "outside").G.Known {
		t.Fatal("inside the warm-up the sensor still reads the unit")
	}
	h.Settle(430)
	if h.W.Var("u2", "outside").G.Known {
		t.Fatal("the reading taken inside the warm-up is dropped, not folded later")
	}
	h.Ingest(st("sensor.lab_outside_temperature", "5.0"), 440)
	h.Settle(450)
	if h.State().Units["u2"].Outside == nil || *h.State().Units["u2"].Outside != 5 {
		t.Fatalf("%+v", h.State().Units["u2"])
	}
	if p := h.B.Weight("out_cold")([]string{"u2"}, nil); p < 0.99 {
		t.Fatal(p)
	}
}

// TestPowerPortsPerKind: a level over unit_on gets the units' atoms only (a light in Home Assistant never
// leaks power(…, l3) into a package whose level pred takes units), in the runtime's spelling, one true
// per known key and every name false for a key the world has no reading of.
func TestPowerPortsPerKind(t *testing.T) {
	h := wired(t)
	h.B.Join(&sw.Manifest{Name: "air", Levels: map[string]sw.LevelSpec{"power": {
		From: map[string]string{"belief": "unit_on"}, At: []float64{0.05, 0.95}, Names: []string{"off", "unconfirmed", "on"}}}})
	h.Ingest(st("fan.lab_supply_fan", "on"), 1)
	h.Ingest(st("fan.lab_extract_fan", "on"), 1)
	h.Ingest(st("light.lab", "on"), 1)
	h.Settle(1)
	got := h.B.LevelAtoms("air")
	for a := range got {
		if !strings.HasSuffix(a, ",u1)") && !strings.HasSuffix(a, ",u2)") {
			t.Fatalf("a non-unit key in a unit level: %s", a)
		}
	}
	if !got["power(on,u2)"] || got["power(off,u2)"] || got["power(unconfirmed,u2)"] {
		t.Fatalf("u2: %v", got)
	}
	h.Command("u2", "power", "off", 2)
	if got := h.B.LevelAtoms("air"); !got["power(unconfirmed,u2)"] || got["power(on,u2)"] {
		t.Fatalf("a commanded switch is unconfirmed until read back: %v", got)
	}
	if v, ok := got["power(on,u1)"]; ok && v {
		t.Fatalf("u1 has no reading: %v", got)
	}
}
