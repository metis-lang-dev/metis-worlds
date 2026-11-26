package home

import (
	"reflect"
	"testing"
)

// TestASnapshotContinuesTheDay: at every point of the day, a world restored from a snapshot
// hashes as the original and, given the rest of the day, gives the same checkpoints and outputs
// as the world that never stopped.
func TestASnapshotContinuesTheDay(t *testing.T) {
	evs := dayEvents(t)
	full := run(t, evs)
	for cut := 0; cut < len(evs); cut += 7 {
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
			out, err := r.Apply(evs[i])
			if err != nil {
				t.Fatalf("cut %d, event %d: %v", cut, i, err)
			}
			if r.Hash() != full.Hashes[i] {
				t.Fatalf("cut %d: after event %d (%s) the restored world differs", cut, i, evs[i].Kind)
			}
			if !reflect.DeepEqual(out, full.Outs[i]) {
				t.Fatalf("cut %d: event %d's output differs:\n%+v\n%+v", cut, i, out, full.Outs[i])
			}
		}
	}
}

// TestARestoreRefusesAnotherWorld: a snapshot of a world built otherwise does not restore.
func TestARestoreRefusesAnotherWorld(t *testing.T) {
	h := dayHome(t)
	snap, _ := h.Snapshot()
	snap[len(snap)/2] ^= 0xff
	if err := dayHome(t).Restore(snap); err == nil {
		t.Fatal("a damaged snapshot restored")
	}
}
