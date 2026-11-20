"""Persistent weekly deadline/backoff policy; no network or continuously polling timer."""
from threading import RLock
import math
import time

WEEK=7*24*60*60


class WorldUpdatePolicy:
    def __init__(self, repository, clock=time.time):
        self.repository,self.clock,self.lock=repository,clock,RLock()
        self.state={'schemaVersion':1,'enabled':True,'lastSuccessfulCheck':None,'lastDataUpdate':None,
            'failures':0,'nextAttempt':0,'lastError':None}
        try:
            saved=repository.load()
            if saved is not None:
                if not isinstance(saved,dict) or saved.get('schemaVersion')!=1 or not isinstance(saved.get('enabled'),bool):raise ValueError('Invalid update settings')
                for key in ('lastSuccessfulCheck','lastDataUpdate','nextAttempt'):
                    value=saved.get(key)
                    if value is not None and (isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0):raise ValueError('Invalid update timestamp')
                if not isinstance(saved.get('failures'),int) or not 0<=saved['failures']<=4:raise ValueError('Invalid update retry count')
                self.state.update({key:saved[key] for key in self.state if key in saved})
        except (OSError,ValueError,TypeError):
            self.state['enabled']=False
            self.state['lastError']='Update settings could not be read; existing file preserved.'

    @property
    def enabled(self):return self.state['enabled']

    def _save(self, changes):
        with self.lock:
            state=dict(self.state);state.update(changes)
            self.repository.save(state);self.state=state

    def set_enabled(self,value):self._save({'enabled':bool(value)})

    def deadline(self):
        checked=self.state['lastSuccessfulCheck']
        return max((checked+WEEK if checked is not None else 0),self.state['nextAttempt'] or 0)

    def due(self):return self.enabled and self.clock()>=self.deadline()

    def success(self,changed):
        now=self.clock();changes={'lastSuccessfulCheck':now,'failures':0,'nextAttempt':0,'lastError':None}
        if changed:changes['lastDataUpdate']=now
        self._save(changes)

    def failure(self,error):
        with self.lock:
            count=min(4,self.state['failures']+1)
            self._save({'failures':count,'nextAttempt':self.clock()+(3600,21600,86400,WEEK)[count-1],
                'lastError':str(error)[:800]})
