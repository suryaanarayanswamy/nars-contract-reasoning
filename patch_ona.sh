#!/bin/bash
# Builds a copy of ONA with bigger limits. The default build silently DROPS statements whose term tree is larger than 64 slots
# and cuts atom names at 32 characters; the full-meaning Narsese statements need more room.
#   bash patch_ona.sh ~/Downloads/OpenNARS-for-Applications
# then:  export ONA_PATH=<the folder it prints>
SRC="${1:-$HOME/Downloads/OpenNARS-for-Applications}"
DST="${SRC%/}_big"
[ -d "$SRC" ] || { echo "ONA folder not found: $SRC"; exit 1; }
LOG=/tmp/ona_big_build.log; : > "$LOG"
try_build () {   # $1 = COMPOUND_TERM_SIZE_MAX, $2 = ATOMS_MAX, rest = extra compiler flags
  local C="$1" A="$2"; shift 2
  rm -rf "$DST"; cp -R "$SRC" "$DST"; cd "$DST" || return 1
  sed -i.bak "s/#define COMPOUND_TERM_SIZE_MAX [0-9]*/#define COMPOUND_TERM_SIZE_MAX $C/; s/#define ATOMS_MAX [0-9]*/#define ATOMS_MAX $A/" src/Config.h
  rm -f NAR
  echo "== trying COMPOUND_TERM_SIZE_MAX=$C ATOMS_MAX=$A $*" >> "$LOG"
  bash build.sh "$@" >> "$LOG" 2>&1
  [ -x NAR ] || return 1
  # smoke test: a build that compiles can still fail to start (macOS cannot map a binary with huge tables)
  printf '<a --> b>.\n<a --> b>?\n5\n' | ./NAR shell 2>/dev/null | grep -q "^Answer:" || { echo "   (built, but does not run: $C/$A)" >> "$LOG"; echo "   $C/$A builds but does not start here, trying smaller"; return 1; }
}
if try_build 256 4095 || try_build 256 1023 || try_build 256 511 || try_build 128 1023 || try_build 128 511 || try_build 128 255 || { [ "$(uname)" = "Linux" ] && try_build 256 4095 -mcmodel=medium; }; then
  grep -n "define COMPOUND_TERM_SIZE_MAX\|define ATOMS_MAX " "$DST/src/Config.h"
  echo "OK. Now run:   export ONA_PATH=\"$DST\""
else
  echo "Build failed. First errors:"; grep -n -m6 "error" "$LOG"; echo "(full log: $LOG)"; exit 1
fi
