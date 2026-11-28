package semworld

import (
	"fmt"
	"sort"
	"strconv"
	"strings"
	"time"
)

// ── the schedule: what is due when, on the world's own clock ──
//
// An entry is set by a member (its owner) for one of its handles (its slot): one-shot at a time, or periodic,
// at the clock times of a cron spec (local time) or every so many seconds. The world fires it at its settle,
// whatever the rules are doing: an alarm never waits for an LLM. A due time is a moment, not a level: each
// firing is handed to its owner once (Settle's result, which the settle event's Out carries), to be consumed by
// its rules. A one-shot entry goes when it fires; a periodic one moves to its next time after now, so a periodic
// entry missed several times (the home was down) fires once.
//
// The world never reads a clock: every call takes its `now`. A cron spec is read in the process's local zone.

// Sched is one entry of the schedule.
type Sched struct {
	Owner   string  `json:"owner"`             // the member that set it: its firing wakes that member
	Slot    string  `json:"slot"`              // the owner's handle for it
	Subject string  `json:"subject,omitempty"` // what it is for, in the person's words
	At      float64 `json:"at,omitempty"`      // when it is next due (s); a periodic entry without one: its next after now
	Cron    string  `json:"cron,omitempty"`    // periodic at clock times: minute hour day-of-month month day-of-week
	Every   float64 `json:"every,omitempty"`   // periodic every so many seconds
	Fired   int     `json:"fired,omitempty"`   // times it has been due
}

// Periodic: the entry comes back after it fires.
func (e Sched) Periodic() bool { return e.Cron != "" || e.Every > 0 }

// Schedule is the world's schedule, its entries by owner/slot.
type Schedule struct {
	Entries map[string]*Sched
}

// NewSchedule is an empty schedule.
func NewSchedule() *Schedule { return &Schedule{Entries: map[string]*Sched{}} }

func schedKey(owner, slot string) string { return owner + "/" + slot }

// Set enters E at NOW (replacing the owner's entry for the slot): a periodic entry's first time is its next after
// NOW unless it has one.
func (s *Schedule) Set(e Sched, now float64) error {
	if e.Owner == "" || e.Slot == "" {
		return fmt.Errorf("schedule: an entry needs its owner and its slot")
	}
	if e.Cron != "" && e.Every > 0 {
		return fmt.Errorf("schedule: %s/%s: a cron spec or a period, not both", e.Owner, e.Slot)
	}
	if e.Every < 0 {
		return fmt.Errorf("schedule: %s/%s: a negative period", e.Owner, e.Slot)
	}
	if e.Cron != "" {
		c, err := ParseCron(e.Cron)
		if err != nil {
			return fmt.Errorf("schedule: %s/%s: %w", e.Owner, e.Slot, err)
		}
		if e.At == 0 {
			e.At = c.after(now)
		}
	} else if e.Every > 0 && e.At == 0 {
		e.At = now + e.Every
	}
	if e.At == 0 {
		return fmt.Errorf("schedule: %s/%s: no time", e.Owner, e.Slot)
	}
	e.Fired = 0
	s.Entries[schedKey(e.Owner, e.Slot)] = &e
	return nil
}

// Cancel takes the owner's entry for the slot off (false: there was none).
func (s *Schedule) Cancel(owner, slot string) bool {
	k := schedKey(owner, slot)
	_, ok := s.Entries[k]
	delete(s.Entries, k)
	return ok
}

// Get is the owner's entry for the slot.
func (s *Schedule) Get(owner, slot string) (Sched, bool) {
	e, ok := s.Entries[schedKey(owner, slot)]
	if !ok {
		return Sched{}, false
	}
	return *e, true
}

// Of are the owner's entries, by slot.
func (s *Schedule) Of(owner string) []Sched {
	var out []Sched
	for _, k := range sortedKeys(s.Entries) {
		if e := s.Entries[k]; e.Owner == owner {
			out = append(out, *e)
		}
	}
	return out
}

// Settle fires what is due at NOW, in order of its time (then owner and slot): each firing as the entry was when
// it fell due. A one-shot entry goes; a periodic one moves to its next time after NOW.
func (s *Schedule) Settle(now float64) []Sched {
	var due []Sched
	for _, k := range sortedKeys(s.Entries) {
		e := s.Entries[k]
		if e.At > now {
			continue
		}
		e.Fired++
		due = append(due, *e)
		switch {
		case e.Cron != "":
			c, _ := ParseCron(e.Cron) // checked at Set
			e.At = c.after(now)
		case e.Every > 0:
			for e.At <= now {
				e.At += e.Every
			}
		default:
			delete(s.Entries, k)
		}
	}
	sort.SliceStable(due, func(i, j int) bool { return due[i].At < due[j].At })
	return due
}

// HashText is the schedule as sorted text (a checkpoint's).
func (s *Schedule) HashText() string {
	var b strings.Builder
	for _, k := range sortedKeys(s.Entries) {
		fmt.Fprintf(&b, "Q %s %v\n", k, *s.Entries[k])
	}
	return b.String()
}

// Cron is a parsed cron spec: the allowed minutes, hours, days of the month, months and days of the week.
type Cron struct {
	min, hour, dom, mon, dow uint64
	domAny, dowAny           bool
}

// ParseCron reads a five-field cron spec (minute hour day-of-month month day-of-week; each field *, a value, a
// range a-b, a step */n or a-b/n, or a list of them; day-of-week 0-7 with 0 and 7 Sunday, or sun..sat; a month
// 1-12 or jan..dec). As cron has it, when both day fields are restricted a day matching either is a day.
func ParseCron(spec string) (Cron, error) {
	f := strings.Fields(spec)
	if len(f) != 5 {
		return Cron{}, fmt.Errorf("cron %q: five fields (minute hour day month weekday)", spec)
	}
	var c Cron
	var err error
	if c.min, err = cronField(f[0], 0, 59, nil); err != nil {
		return Cron{}, fmt.Errorf("cron %q: minute: %w", spec, err)
	}
	if c.hour, err = cronField(f[1], 0, 23, nil); err != nil {
		return Cron{}, fmt.Errorf("cron %q: hour: %w", spec, err)
	}
	if c.dom, err = cronField(f[2], 1, 31, nil); err != nil {
		return Cron{}, fmt.Errorf("cron %q: day of the month: %w", spec, err)
	}
	if c.mon, err = cronField(f[3], 1, 12, months); err != nil {
		return Cron{}, fmt.Errorf("cron %q: month: %w", spec, err)
	}
	if c.dow, err = cronField(f[4], 0, 7, weekdays); err != nil {
		return Cron{}, fmt.Errorf("cron %q: day of the week: %w", spec, err)
	}
	if c.dow&(1<<7) != 0 {
		c.dow |= 1 // 7 is Sunday too
	}
	c.domAny, c.dowAny = f[2] == "*", f[4] == "*"
	return c, nil
}

var (
	weekdays = map[string]int{"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}
	months   = map[string]int{"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
		"sep": 9, "oct": 10, "nov": 11, "dec": 12}
)

func cronField(f string, lo, hi int, names map[string]int) (uint64, error) {
	val := func(s string) (int, error) {
		if n, ok := names[strings.ToLower(s)]; ok {
			return n, nil
		}
		n, err := strconv.Atoi(s)
		if err != nil || n < lo || n > hi {
			return 0, fmt.Errorf("%q is not in %d-%d", s, lo, hi)
		}
		return n, nil
	}
	var bits uint64
	for _, part := range strings.Split(f, ",") {
		r, step := part, 1
		if a, b, ok := strings.Cut(part, "/"); ok {
			n, err := strconv.Atoi(b)
			if err != nil || n < 1 {
				return 0, fmt.Errorf("a step %q", b)
			}
			r, step = a, n
		}
		from, to := lo, hi
		switch {
		case r == "*":
		case strings.Contains(r, "-"):
			a, b, _ := strings.Cut(r, "-")
			var err error
			if from, err = val(a); err != nil {
				return 0, err
			}
			if to, err = val(b); err != nil {
				return 0, err
			}
			if to < from {
				return 0, fmt.Errorf("a range %q backwards", r)
			}
		default:
			n, err := val(r)
			if err != nil {
				return 0, err
			}
			from, to = n, n
			if step > 1 {
				to = hi
			}
		}
		for i := from; i <= to; i += step {
			bits |= 1 << uint(i)
		}
	}
	return bits, nil
}

func (c Cron) day(t time.Time) bool {
	dom, dow := c.dom&(1<<uint(t.Day())) != 0, c.dow&(1<<uint(t.Weekday())) != 0
	switch {
	case c.domAny && c.dowAny:
		return true
	case c.domAny:
		return dow
	case c.dowAny:
		return dom
	}
	return dom || dow
}

// Next is the first time after T that the spec allows (zero: none within five years, as for a 31 February).
func (c Cron) Next(t time.Time) time.Time {
	t = t.Truncate(time.Minute).Add(time.Minute)
	end := t.AddDate(5, 0, 0)
	for t.Before(end) {
		switch {
		case c.mon&(1<<uint(t.Month())) == 0:
			t = time.Date(t.Year(), t.Month()+1, 1, 0, 0, 0, 0, t.Location())
		case !c.day(t):
			t = time.Date(t.Year(), t.Month(), t.Day()+1, 0, 0, 0, 0, t.Location())
		case c.hour&(1<<uint(t.Hour())) == 0:
			t = time.Date(t.Year(), t.Month(), t.Day(), t.Hour()+1, 0, 0, 0, t.Location())
		case c.min&(1<<uint(t.Minute())) == 0:
			t = t.Add(time.Minute)
		default:
			return t
		}
	}
	return time.Time{}
}

// after is Next after NOW (s), in local time (0: none).
func (c Cron) after(now float64) float64 {
	n := c.Next(time.Unix(int64(now), 0).In(time.Local))
	if n.IsZero() {
		return 0
	}
	return float64(n.Unix())
}
