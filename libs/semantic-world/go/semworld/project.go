package semworld

import (
	"fmt"
	"math"
	"sort"
	"strings"
)

// ── the LLM face: the ENVIRONMENT / REASONING projection, a pure function of the world ──
//
// One line per variable an adapter phrases, keyed (the env stream replaces per key), saying the value
// with its confidence, its age and its source; a member's conclusions project as reasoning lines.
// The same beliefs the ports quantise, so the dialog and Metis read one source of truth.

// Line is one projected line.
type Line struct {
	Stream string  `json:"stream"` // env | reasoning
	Key    string  `json:"key"`
	Text   string  `json:"text"`
	P      float64 `json:"p"`   // the confidence of what the line says
	Age    float64 `json:"age"` // s since its evidence
	Src    string  `json:"src"`
}

// Phrase is an adapter's wording of a variable: its subject and, per value, the words; ok false skips
// it. UNIT and DIGITS format a VGauss.
type Phrase struct {
	Subject string
	Words   map[string]string // value → words ("on" → "running")
	Unit    string
	Digits  int
	// Absent is said instead of a value when the variable is not wired ("not in Home Assistant yet").
	Absent string
}

// Phraser is an adapter's wording of a variable.
type Phraser func(e *Entry, name string, v *Var) (Phrase, bool)

// Ages are said coarsely: the LLM needs "just now" vs "an hour ago", not seconds.
func age(s float64) string {
	switch {
	case s < 0:
		return "now"
	case s < 90:
		return "just now"
	case s < 3600:
		return fmt.Sprintf("%.0f min ago", s/60)
	case s < 86400:
		return fmt.Sprintf("%.0f h ago", s/3600)
	}
	return fmt.Sprintf("%.0f d ago", s/86400)
}

// Confidence words: what the LLM may say flatly, what it must hedge.
func sureness(p float64) string {
	switch {
	case p >= 0.95:
		return "sure"
	case p >= 0.8:
		return "likely"
	case p >= 0.6:
		return "probably"
	}
	return "unsure"
}

func srcWord(s Source) string {
	switch s.Kind {
	case "sensor":
		return "sensor"
	case "command":
		return "commanded, not yet confirmed"
	case "person":
		return "said by " + s.Who
	case "metis":
		return "inferred by " + s.Who
	case "prior":
		return "no reading yet"
	}
	return s.Kind
}

// Project is the world's lines at NOW (sorted by key).
func Project(w *World, now float64, phrase Phraser) []Line {
	var out []Line
	for _, id := range sortedKeys(w.Entries) {
		e := w.Entries[id]
		for _, name := range sortedKeys(e.Vars) {
			v := e.Vars[name]
			if e.Kind == KInferred {
				if v.Fact {
					out = append(out, Line{Stream: "reasoning", Key: Key(id, name), P: 1, Age: now - v.At,
						Src: srcWord(v.Src), Text: fmt.Sprintf("%s holds %s%s", e.Name, name, ruleOf(v.Src))})
				}
				continue
			}
			ph, ok := phrase(e, name, v)
			if !ok {
				continue
			}
			out = append(out, projectVar(id, name, v, ph, now))
		}
	}
	return out
}

func ruleOf(s Source) string {
	if s.Ref != "" {
		return " (rule " + s.Ref + ")"
	}
	return ""
}

func projectVar(id, name string, v *Var, ph Phrase, now float64) Line {
	l := Line{Stream: "env", Key: Key(id, name), Age: now - v.At, Src: srcWord(v.Src)}
	if ph.Absent != "" {
		l.Text = ph.Subject + ": " + ph.Absent
		return l
	}
	if v.Src.Kind == "prior" {
		l.Text = ph.Subject + ": unknown (no reading yet)"
		return l
	}
	tail := func(p float64) string {
		parts := []string{sureness(p), srcWord(v.Src), age(now - v.At)}
		if v.Unsure {
			parts = append(parts, "no fresh reading possible")
		}
		return " (" + strings.Join(parts, ", ") + ")"
	}
	word := func(x string) string {
		if w, ok := ph.Words[x]; ok {
			return w
		}
		return x
	}
	switch v.Kind {
	case VCat:
		top, p := v.Top()
		l.P = p
		if p < 0.6 { // say the spread, not a value
			type kv struct {
				k string
				p float64
			}
			var xs []kv
			for _, x := range v.Values {
				xs = append(xs, kv{x, v.Cat[x]})
			}
			sort.SliceStable(xs, func(i, j int) bool { return xs[i].p > xs[j].p })
			var s []string
			for _, x := range xs {
				if x.p >= 0.05 {
					s = append(s, fmt.Sprintf("%s %.0f%%", word(x.k), 100*x.p))
				}
			}
			l.Text = ph.Subject + ": unsure — " + strings.Join(s, " / ") + " (" + srcWord(v.Src) + ", " + age(now-v.At) + ")"
			return l
		}
		l.Text = ph.Subject + ": " + word(top) + tail(p)
	case VOdds:
		p := P(v.Odds)
		val, conf := "yes", p
		if p < 0.5 {
			val, conf = "no", 1-p
		}
		l.P = conf
		l.Text = ph.Subject + ": " + word(val) + tail(conf)
	case VGauss:
		if !v.G.Known {
			l.Text = ph.Subject + ": unknown (no reading yet)"
			return l
		}
		sd := v.G.Sd()
		l.P = math.Max(0, 1-sd/3) // a rough confidence: ±3 units is no knowledge
		f := "%." + fmt.Sprint(ph.Digits) + "f"
		parts := []string{srcWord(v.Src), age(now - v.At)}
		if v.Unsure {
			parts = append(parts, "no fresh reading possible")
		}
		l.Text = ph.Subject + ": " + fmt.Sprintf(f, v.G.Mean) + ph.Unit + fmt.Sprintf(" ±"+f, sd) + " (" +
			strings.Join(parts, ", ") + ")"
	}
	return l
}
