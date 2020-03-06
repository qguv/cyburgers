# cyburgers

view the balance of a shared bunq account

### run (shell)

```bash
git clone ssh://github.com/qguv/cyburgers
pipenv install
BUNQ_API_KEY=000000000000000000 pipenv run python cyburgers.py &
firefox https://localhost:5957/cyburgers/balance
fg
```

### run (systemd)

```bash
sudo cp systemd/system/cyburgers.service /etc/systemd/system/
sudo systemctl enable --now cyburgers
```


### deploy

```bash
ssh cloud.guvernator.net -- bash -c 'cd dev/cyburgers && git fetch -p origin && git reset --hard origin/master && sudo systemctl reload cyburgers'
```
