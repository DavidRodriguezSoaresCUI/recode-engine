@echo off

echo Rebuilding source directory
RD /S /Q ".\source"
sphinx-apidoc -f --maxdepth 4 --separate --doc-project "recode-engine" --doc-author "DavidRodriguezSoaresCUI" --full -o source ../src/recode-engine
python sphinx-patch-conf.py

echo Rebuilding HTML build
RD /S /Q ".\build"
sphinx-build source build
echo Done ! Open build/index.html to see documentation