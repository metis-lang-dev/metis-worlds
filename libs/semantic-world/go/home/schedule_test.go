package home

import (
	"reflect"
	"testing"
	"time"

	sw "github.com/metis-lang-dev/metis-worlds/libs/semantic-world/go/semworld"
)

// scheduleDay: the day's events with a schedule in them (a countdown, a daily alarm, a period, one cancelled).
func scheduleDay(t *testing.T) []Event {
	evs := dayEvents(t)
	t0 := evs[0].At
	var out []Event
	out = append(out,
		Event{At: t0, Kind: "schedule", Sched: &sw.Sched{Owner: "timers", Slot: "k1", Subject: "the tea", At: t0 + 120}},
		Event{At: t0, Kind: "schedule", Sched: &sw.Sched{Owner: "timers", Slot: "k2", Subject: "wake up", Cron: "*/5 * * * *"}},
		Event{At: t0, Kind: "schedule", Sched: &sw.Sched{Owner: "routine", Slot: "stretch", Every: 240}},
		Event{At: t0, Kind: "schedule", Sched: &sw.Sched{Owner: "timers", Slot: "k3", At: t0 + 60}},
		Event{At: t0, Kind: "unschedule", Member: "timers", ID: "k3"})
	return append(out, evs...)
}

// TestTheScheduleIsTheWorlds: what is due falls due at the world's settle, each firing in one settle's Out only,
// and a world restored from a snapshot at any point carries the schedule on as the one that never stopped.
func TestTheScheduleIsTheWorlds(t *testing.T) {
	old := time.Local
	time.Local = time.FixedZone("CET", 3600)
	t.Cleanup(func() { time.Local = old })
	evs := scheduleDay(t)
	full := run(t, evs)
	fired := map[string]int{}
	for i, o := range full.Outs {
		if len(o.Due) > 0 && evs[i].Kind != "settle" {
			t.Fatalf("event %d (%s) has due entries", i, evs[i].Kind)
		}
		for _, d := range o.Due {
			if d.At > evs[i].At {
				t.Fatalf("event %d: %s/%s fired before its time", i, d.Owner, d.Slot)
			}
			fired[d.Owner+"/"+d.Slot]++
		}
	}
	span := evs[len(evs)-1].At - evs[0].At
	t.Logf("fired %v over %.0f s", fired, span)
	if fired["timers/k1"] != 1 || fired["timers/k3"] != 0 {
		t.Fatalf("fired: %v (over %.0f s)", fired, span)
	}
	if span > 600 && (fired["timers/k2"] < 2 || fired["routine/stretch"] < 2) {
		t.Fatalf("the periodic entries: %v (over %.0f s)", fired, span)
	}
	for cut := 0; cut < len(evs); cut += 11 {
		h := dayHome(t)
		for _, ev := range evs[:cut] {
			h.Apply(ev)
		}
		snap, err := h.Snapshot()
		if err != nil {
			t.Fatal(err)
		}
		r := dayHome(t)
		if err := r.Restore(snap); err != nil {
			t.Fatalf("cut %d: %v", cut, err)
		}
		for i := cut; i < len(evs); i++ {
			out, _ := r.Apply(evs[i])
			if r.Hash() != full.Hashes[i] || !reflect.DeepEqual(out, full.Outs[i]) {
				t.Fatalf("cut %d: event %d (%s) differs", cut, i, evs[i].Kind)
			}
		}
		// a world built otherwise keeps the schedule (and the taste) from the snapshot
		k := New(dayHome(t).M, DefaultParams)
		if err := k.RestoreTaste(snap); err != nil {
			t.Fatal(err)
		}
		if !reflect.DeepEqual(k.W.Sched.Entries, h.W.Sched.Entries) {
			t.Fatalf("cut %d: RestoreTaste: %+v, want %+v", cut, k.W.Sched.Entries, h.W.Sched.Entries)
		}
	}
	if _, err := dayHome(t).Apply(Event{Kind: "schedule"}); err == nil {
		t.Fatal("a schedule event without an entry applied")
	}
	if _, err := dayHome(t).Apply(Event{Kind: "schedule", Sched: &sw.Sched{Owner: "t", Slot: "k1", Cron: "nope"}}); err == nil {
		t.Fatal("a bad cron spec applied")
	}
}
