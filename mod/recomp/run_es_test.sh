#!/bin/bash
# LIVE test of the translation hook (translation_es.h).  Portable version:
# derives the paths from the script location (run from anywhere).
#
# Usage:  bash mod/recomp/run_es_test.sh [seconds]
set -u
SECS="${1:-90}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
F2="$REPO/extract/f2"
cd "$F2" || exit 1
cp -f recomp/out/build/local/InfiniteUndiscoveryRecomp.exe run/
cp -f recomp/out/build/local/*.dll run/
cd run || exit 1
LOG="EUROPE/logs/iu_trace.log"
rm -f "$LOG"
echo "== ejecutando ${SECS}s  IU_ES=1 =="
IU_ES=1 IU_TRACE=1 IU_TRACE_DIR="$F2/run/EUROPE/logs" \
  timeout "$SECS" ./InfiniteUndiscoveryRecomp.exe > es_run.log 2>&1
echo "exit=$? (124 = timeout, esperado)"
echo "== lineas del hook (ES: ...) =="
grep -E "ES:" "$LOG" 2>/dev/null | head -40
echo "== ultimas lineas del runtime =="
tail -6 es_run.log 2>/dev/null
