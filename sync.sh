#!/bin/bash
git add . git commit -m "auto 
$(date '+%Y-%m-%d %H:%M:%S')" || 
true
git push
