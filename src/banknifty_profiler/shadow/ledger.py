from __future__ import annotations
import json,os,tempfile
from pathlib import Path
from threading import Lock

class AppendOnlyLedger:
 def __init__(self,path:Path):self.path=path;path.parent.mkdir(parents=True,exist_ok=True);self._lock=Lock()
 def append(self,row:dict)->None:
  self.append_many([row])
 def append_many(self,rows)->None:
  encoded=b''.join((json.dumps(row,sort_keys=True,separators=(',',':'))+'\n').encode() for row in rows)
  if not encoded:return
  with self._lock,self.path.open('ab') as handle:handle.write(encoded);handle.flush();os.fsync(handle.fileno())
 def rows(self):
  if not self.path.exists():return []
  with self.path.open() as h:return [json.loads(line) for line in h if line.strip()]

def atomic_json(path:Path,value:dict)->None:
 path.parent.mkdir(parents=True,exist_ok=True)
 fd,name=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
 try:
  with os.fdopen(fd,'w') as h:json.dump(value,h,sort_keys=True,separators=(',',':'));h.write('\n');h.flush();os.fsync(h.fileno())
  os.replace(name,path)
  directory=os.open(path.parent,os.O_RDONLY)
  try:os.fsync(directory)
  finally:os.close(directory)
 finally:
  if os.path.exists(name):os.unlink(name)
