#!/bin/bash
cd ~/aaa python run.py git add . 
git commit -m "run $(date 
'+%Y-%m-%d %H:%M')" || true
git push
