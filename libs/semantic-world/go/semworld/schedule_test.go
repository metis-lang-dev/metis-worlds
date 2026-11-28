package semworld

import (
	"testing"
	"time"
)

// inZone runs the test in a fixed local zone (a cron spec is read in local time).
func inZone(t *testing.T) *time.Location {
	old := time.Local
	time.Local = time.FixedZone("CET", 3600)
	t.Cleanup(func() { time.Local = old })
	return time.Local
}

func TestCronNext(t *testing.T) {
	loc := inZone(t)
	at := func(s string) time.Time {
		x, err := time.ParseInLocation("2006-01-02 15:04", s, loc)
		if err != nil {
			t.Fatal(err)
		}
		return x
	}
	for _, c := range []struct{ spec, from, want string }{
		{"30 7 * * *", "2026-11-28 07:29", "2026-11-28 07:30"},
		{"30 7 * * *", "2026-11-28 07:30", "2026-11-29 07:30"},  // after, never at
		{"0 7 * * 1-5", "2026-11-27 08:00", "2026-11-30 07:00"}, // Friday → Monday
		{"0 9 * * sat,sun", "2026-11-25 10:00", "2026-11-28 09:00"},
		{"0 9 * * 7", "2026-11-28 10:00", "2026-11-29 09:00"}, // 7 is Sunday
		{"*/15 * * * *", "2026-11-28 10:07", "2026-11-28 10:15"},
		{"0 0 1 * *", "2026-11-28 10:00", "2026-12-01 00:00"},
		{"0 12 13 * 5", "2026-11-28 10:00", "2026-12-04 12:00"}, // both days restricted: either
		{"0 8 * dec *", "2026-11-28 10:00", "2026-12-01 08:00"},
		{"0 23 * * *", "2026-12-31 23:30", "2027-01-01 23:00"},
	} {
		c0, err := ParseCron(c.spec)
		if err != nil {
			t.Fatalf("%s: %v", c.spec, err)
		}
		if got := c0.Next(at(c.from)); !got.Equal(at(c.want)) {
			t.Errorf("%q after %s: %s, want %s", c.spec, c.from, got.Format("2006-01-02 15:04"), c.want)
		}
	}
	for _, bad := range []string{"", "* * * *", "60 * * * *", "* 24 * * *", "* * 0 * *", "* * * 13 *", "* * * * 8",
		"5-1 * * * *", "*/0 * * * *", "x * * * *"} {
		if _, err := ParseCron(bad); err == nil {
			t.Errorf("%q parsed", bad)
		}
	}
	c, _ := ParseCron("0 0 31 2 *")
	if n := c.Next(at("2026-01-01 00:00")); !n.IsZero() {
		t.Errorf("31 February: %s", n)
	}
}

func TestTheScheduleFiresEachEntryOnce(t *testing.T) {
	loc := inZone(t)
	now := float64(time.Date(2026, 11, 28, 7, 0, 0, 0, loc).Unix())
	s := NewSchedule()
	must := func(e Sched) {
		if err := s.Set(e, now); err != nil {
			t.Fatal(err)
		}
	}
	must(Sched{Owner: "timers", Slot: "k1", Subject: "the tea", At: now + 300})
	must(Sched{Owner: "timers", Slot: "k2", Subject: "wake up", Cron: "30 7 * * *"})
	must(Sched{Owner: "routine", Slot: "stretch", Every: 600})
	if e, _ := s.Get("timers", "k2"); e.At != now+1800 {
		t.Fatalf("a cron entry's first time: %v", e.At-now)
	}
	if due := s.Settle(now + 299); len(due) != 0 {
		t.Fatalf("early: %+v", due)
	}
	due := s.Settle(now + 300)
	if len(due) != 1 || due[0].Slot != "k1" || due[0].Fired != 1 {
		t.Fatalf("at 5 min: %+v", due)
	}
	if _, ok := s.Get("timers", "k1"); ok {
		t.Fatal("a one-shot entry stays after it fired")
	}
	if due := s.Settle(now + 301); len(due) != 0 {
		t.Fatalf("fired twice: %+v", due)
	}
	// the home was down for an hour: each periodic entry fires once, in order of its time, and moves past now
	due = s.Settle(now + 3600)
	if len(due) != 2 || due[0].Slot != "stretch" || due[1].Slot != "k2" {
		t.Fatalf("after an hour: %+v", due)
	}
	if e, _ := s.Get("routine", "stretch"); e.At != now+4200 || e.Fired != 1 {
		t.Fatalf("the period's next: %+v", e)
	}
	if e, _ := s.Get("timers", "k2"); e.At != now+1800+86400 {
		t.Fatalf("the cron's next: %v", e.At-now)
	}
	if !s.Cancel("timers", "k2") || s.Cancel("timers", "k2") {
		t.Fatal("cancel")
	}
	if len(s.Of("timers")) != 0 || len(s.Of("routine")) != 1 {
		t.Fatalf("entries: %+v", s.Entries)
	}
	for _, bad := range []Sched{{Slot: "k1", At: 1}, {Owner: "t", Slot: "k1"}, {Owner: "t", Slot: "k1", Cron: "x"},
		{Owner: "t", Slot: "k1", Cron: "* * * * *", Every: 60}, {Owner: "t", Slot: "k1", Every: -1}} {
		if err := s.Set(bad, now); err == nil {
			t.Errorf("set %+v", bad)
		}
	}
}
