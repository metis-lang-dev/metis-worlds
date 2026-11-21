// semworld-replay runs a scripted day of the home through the semantic world and prints what each
// reader would get: the LLM's env/reasoning lines (as the stream door's JSON lines with -door), each
// member's level do-lines and whether it beats (spec 15 rule 1), and the surprises.
//
//	semworld-replay -map testdata/home.wired.map.json -member comfort=testdata/comfort.domain.yaml testdata/home.replay.jsonl
//
// Script lines: {"t": s, "ha": {HA state}} | {"t", "command": {"id","var","value"}} |
// {"t", "report": {"who","id","var","value","ref"}} | {"t", "conclude": {"member","fact","on","rule"}} |
// {"t", "feed": "down"} | {"t", "settle": true}  (every line after the first settles at its t first)
package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"regexp"
	"sort"
	"strings"

	"github.com/metis-lang-dev/metis-worlds/libs/semantic-world/go/home"
	sw "github.com/metis-lang-dev/metis-worlds/libs/semantic-world/go/semworld"
)

type step struct {
	T        float64                                    `json:"t"`
	HA       *home.HAState                              `json:"ha"`
	Command  *struct{ ID, Var, Value string }           `json:"command"`
	Report   *struct{ Who, ID, Var, Value, Ref string } `json:"report"`
	Conclude *struct {
		Member, Fact, Rule string
		On                 bool
	} `json:"conclude"`
	Feed   string `json:"feed"`
	Settle bool   `json:"settle"`
	Note   string `json:"note"`
}

type members []string

func (m *members) String() string     { return strings.Join(*m, ",") }
func (m *members) Set(s string) error { *m = append(*m, s); return nil }

var ages = regexp.MustCompile(`just now|\d+ (min|h|d) ago`)

func main() {
	mapPath := flag.String("map", "testdata/home.wired.map.json", "home.map.json")
	door := flag.Bool("door", false, "print the projection as the stream door's JSON lines only")
	var ms members
	flag.Var(&ms, "member", "NAME=domain.yaml: a member reading the world's ports (repeatable)")
	flag.Parse()
	m, err := home.LoadMap(*mapPath)
	must(err)
	h := home.New(m, home.DefaultParams)
	var names []string
	for _, s := range ms {
		n, p, _ := strings.Cut(s, "=")
		man, err := sw.ReadManifest(p, n)
		must(err)
		must(h.B.Join(man))
		names = append(names, n)
	}
	f, err := os.Open(flag.Arg(0))
	must(err)
	sc := bufio.NewScanner(f)
	said := map[string]string{}
	nsur := 0
	settle := func(t float64) {
		h.Settle(t)
		for _, l := range h.Lines(t) {
			k := ages.ReplaceAllString(l.Text, "")
			if said[l.Key] == k {
				continue
			}
			said[l.Key] = k
			if *door {
				b, _ := json.Marshal(map[string]string{"stream": l.Stream, "key": l.Key, "text": l.Text})
				fmt.Println(string(b))
			} else {
				fmt.Printf("  %-9s %-16s %s\n", l.Stream, l.Key, l.Text)
			}
		}
		if *door {
			return
		}
		for _, n := range names {
			lines := h.B.Lines(n)
			wake := h.B.Wake(n, t)
			if len(lines) > 0 || wake {
				fmt.Printf("  metis     %-16s beat=%v %s\n", n, wake, strings.Join(lines, " "))
			}
		}
		for ; nsur < len(h.W.Surprises); nsur++ {
			s := h.W.Surprises[nsur]
			fmt.Printf("  surprise  %-16s %s: %s\n", s.Key, s.Kind, s.Why)
		}
	}
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		var s step
		must(json.Unmarshal([]byte(line), &s))
		if !*door && s.Note != "" {
			fmt.Printf("t=%-6.0f # %s\n", s.T, s.Note)
		}
		switch {
		case s.HA != nil:
			h.Ingest(*s.HA, s.T)
		case s.Command != nil:
			must(h.Command(s.Command.ID, s.Command.Var, s.Command.Value, s.T))
		case s.Report != nil:
			h.W.Lock()
			_, err := h.W.Report(s.Report.Who, s.Report.ID, s.Report.Var, s.Report.Value, 0, s.Report.Ref, s.T)
			h.W.Unlock()
			must(err)
		case s.Conclude != nil:
			h.W.Lock()
			h.W.Conclude(s.Conclude.Member, s.Conclude.Fact, s.Conclude.On, s.Conclude.Rule, s.T)
			h.W.Unlock()
		case s.Feed == "down":
			h.FeedDown(s.T)
		}
		if s.Settle || s.Note != "" {
			settle(s.T)
		}
	}
	must(sc.Err())
	if !*door {
		st := h.State()
		ks := make([]string, 0, len(st.Units))
		for k := range st.Units {
			ks = append(ks, k)
		}
		sort.Strings(ks)
		for _, k := range ks {
			fmt.Printf("state %s %+v\n", k, st.Units[k])
		}
	}
}

func must(err error) {
	if err != nil {
		fmt.Fprintln(os.Stderr, "semworld-replay:", err)
		os.Exit(1)
	}
}
