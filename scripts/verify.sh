#!/usr/bin/env bash
# End-to-end check against the RUNNING stack (docker compose up).
#
#   scripts/verify.sh                       checks that every service answers and can talk to its neighbours
#   scripts/verify.sh path/to/swing.mp4     also uploads the video, waits for processing, and prints the result
#
# Optional env: ANGLE=face_on|down_the_line (default face_on)  HAND=right|left (default right)
#               API=http://localhost:8080  CV=http://localhost:8000  WEB=http://localhost:5173
set -u

API="${API:-http://localhost:8080}"
CV="${CV:-http://localhost:8000}"
WEB="${WEB:-http://localhost:5173}"
ANGLE="${ANGLE:-face_on}"
HAND="${HAND:-right}"
VIDEO="${1:-}"

FAILS=0
pass() { printf '  [pass] %s\n' "$1"; }
fail() { printf '  [FAIL] %s\n' "$1"; FAILS=$((FAILS + 1)); }

# Print the FIRST value of a key (string/number/bool) from JSON on stdin, without needing jq.
# First match matters: e.g. "id" appears for the analysis before the nested video.
jget() { grep -o "\"$1\": *\"\{0,1\}[^\",}]*" | head -n 1 | sed 's/^[^:]*: *"\{0,1\}//'; }

echo "Service health"
CV_HEALTH="$(curl -fsS -m 5 "$CV/health" 2>/dev/null)"
if [ -n "$CV_HEALTH" ]; then
  pass "cv-service answers ($CV_HEALTH)"
  [ "$(echo "$CV_HEALTH" | jget pose_model_present)" = "true" ] && pass "pose model file present" || fail "pose model file is missing in cv-service (rebuild the image: docker compose build cv-service)"
else
  fail "cv-service did not answer at $CV/health"
fi

if curl -fsS -m 5 "$API/api/health/live" >/dev/null 2>&1; then pass "api is up"; else fail "api did not answer at $API/api/health/live"; fi

API_HEALTH="$(curl -fsS -m 10 "$API/api/health" 2>/dev/null)"
if [ -n "$API_HEALTH" ]; then
  [ "$(echo "$API_HEALTH" | jget database)" = "true" ] && pass "api -> database" || fail "api cannot reach the database"
  [ "$(echo "$API_HEALTH" | jget cvService)" = "true" ] && pass "api -> cv-service" || fail "api cannot reach cv-service"
fi

if curl -fsS -m 5 "$WEB/" >/dev/null 2>&1; then pass "web serves the frontend"; else fail "web did not answer at $WEB/"; fi
if curl -fsS -m 5 "$WEB/api/health/live" >/dev/null 2>&1; then pass "web proxies /api to the api"; else fail "web -> api proxy is not working"; fi

if [ -n "$VIDEO" ]; then
  echo "Processing $VIDEO ($ANGLE, $HAND-handed)"
  if [ ! -f "$VIDEO" ]; then fail "file not found: $VIDEO"; exit 1; fi

  RESPONSE="$(curl -sS -m 600 -X POST "$API/api/analyses" -F "video=@$VIDEO" -F "cameraAngle=$ANGLE" -F "handedness=$HAND")"
  ID="$(echo "$RESPONSE" | jget id)"
  if [ -z "$ID" ]; then fail "upload was rejected: $RESPONSE"; exit 1; fi
  pass "uploaded; analysis id $ID"

  STATUS=""
  for _ in $(seq 1 900); do
    BODY="$(curl -fsS -m 10 "$API/api/analyses/$ID" 2>/dev/null)"
    STATUS="$(echo "$BODY" | jget status)"
    PROGRESS="$(echo "$BODY" | jget progress)"
    printf '\r  status=%s progress=%s%%   ' "$STATUS" "$PROGRESS"
    [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ] && break
    sleep 1
  done
  echo

  if [ "$STATUS" = "completed" ]; then
    pass "analysis completed"
    KP="$(curl -fsS -m 30 "$API/api/analyses/$ID/keypoints" -o /dev/null -w '%{size_download}' 2>/dev/null)"
    [ -n "$KP" ] && [ "$KP" -gt 0 ] && pass "keypoints file served (${KP} bytes)" || fail "keypoints file could not be downloaded"
    echo "  Open: $WEB/analyses/$ID"
    echo "  Quality: $(echo "$BODY" | jget overall)"
  else
    fail "analysis ended as '$STATUS': $(echo "$BODY" | jget error)"
  fi
fi

echo
if [ "$FAILS" -gt 0 ]; then echo "$FAILS check(s) failed."; exit 1; fi
echo "All checks passed."
