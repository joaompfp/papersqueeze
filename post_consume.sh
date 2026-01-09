#!/bin/bash
cd /usr/src/paperless/scripts
python -m papersqueeze process "$DOCUMENT_ID"
