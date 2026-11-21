package semworld

import (
	"encoding/json"
	"os"
	"sync"
	"time"
)

// Store is the map file (store.py): one JSON document, written atomically, read again when another
// process wrote it (an mtime check), and a JSON-lines journal beside it.
type Store struct {
	Path, Journal string
	mu            sync.Mutex
	mtime         int64
}

// Load reads PATH into V when the file changed since the last Load or Save. → whether it was read.
func (s *Store) Load(v any) (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	st, err := os.Stat(s.Path)
	if err != nil {
		return false, nil
	}
	if st.ModTime().UnixNano() == s.mtime {
		return false, nil
	}
	b, err := os.ReadFile(s.Path)
	if err != nil {
		return false, err
	}
	if err := json.Unmarshal(b, v); err != nil {
		return false, err
	}
	s.mtime = st.ModTime().UnixNano()
	return true, nil
}

// Save writes V (sorted keys, indented: encoding/json sorts map keys) through a temporary file.
func (s *Store) Save(v any) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	b, err := json.MarshalIndent(v, "", " ")
	if err != nil {
		return err
	}
	tmp := s.Path + ".tmp"
	if err := os.WriteFile(tmp, b, 0o644); err != nil {
		return err
	}
	if err := os.Rename(tmp, s.Path); err != nil {
		return err
	}
	if st, err := os.Stat(s.Path); err == nil {
		s.mtime = st.ModTime().UnixNano()
	}
	return nil
}

// Log appends one journal row {t, kind, …}.
func (s *Store) Log(kind string, rec map[string]any) error {
	if s.Journal == "" {
		return nil
	}
	row := map[string]any{"t": float64(time.Now().UnixMilli()) / 1000, "kind": kind}
	for k, v := range rec {
		row[k] = v
	}
	b, _ := json.Marshal(row)
	f, err := os.OpenFile(s.Journal, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		return err
	}
	defer f.Close()
	_, err = f.Write(append(b, '\n'))
	return err
}
