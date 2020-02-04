import os
import sys
from time import sleep as wait
from time import time as timestamp
from yaspin import yaspin
import yaml
from subprocess import run
from PyInquirer import prompt, Separator
from typing import List, Tuple, Dict, Optional, Callable

def main():
  templates, products, options, before, after = load_yaml_file()
  
  for step_name, command in iterate_steps(before):
    do_step(step_name, command, show=options['show stdout']['before'])

  for product in iterate_products(templates, products):
    update_project(**product)

  for step_name, command in iterate_steps(before):
    do_step(step_name, command, show=options['show stdout']['after'])

def load_yaml_file():
  if not os.path.isfile('./.updater.yml'):
    print("FATAL: Couldn't file a .updater.yml file in the current directory")
    sys.exit()
    
  with open('./.updater.yml', 'r') as file:
    raw = file.read()
    parsed = yaml.load(raw, Loader=yaml.SafeLoader)
    
  try:
    products = parsed['products']
    templates = parsed.get('templates', {})
    options = parsed.get('options', { 'show stdout': { 'before': False, 'after': True } })
    before = parsed.get('before', [])
    after = parsed.get('after', [])
  except KeyError:
    print('FATAL: Please set your products in .updater.yml')
    sys.exit()
  
  return templates, products, options, before, after
  

def iterate_products(
  templates: dict,
  products: List[dict]
):
  # The yaml is structured like:
  # products:
  # - Verbose product name:
  #     pm2: ...
  #     dir: ...
  #     ...
  cleaned_products = []
  for product in products:
    cleaned_product = {}
    for verbose_name, product in product.items():
      cleaned_product['verbose_name'] = verbose_name
      for key, val in product.items():
        val = _apply_template(key, val, templates)
        key = key.replace(' ', '_')
        cleaned_product[key] = val
      cleaned_products.append(cleaned_product)

  for product in cleaned_products:
    yield product

def _apply_template(
  key: str,
  value: str,
  templates: dict
):
  if key in templates.keys():
    return templates[key] % value
  else:
    return value

def update_project(
  dir: str,
  pm2: Optional[str],
  clone_url: str,
  verbose_name: Optional[str], 
  steps: List[Tuple[str, str, Optional[Dict]]]
):
  ## Print a header
  print('   ', (verbose_name or pm2 or dir).upper())
  ## Create the dir & clone if it doesnt exist
  if not os.path.isdir(dir):
    if prompt([{
      'type': 'confirm',
      'message': "The repository does not exist. Do I clone it?",
      'default': True,
      'name': 'clone'
    }])['clone']:
      git_clone(clone_url, dir)
    else:
      return
  with working_dir(dir):
    ## Check if the repo is up to date
    uptodate = is_up_to_date()
    ## Get choices (if the app is not managed by pm2, we can't show the "Just restart the app" option)
    what_to_do_choices = [
      'Nothing',
      Separator(),
      'Do as if it was not up to date',
    ]
    if pm2: what_to_do_choices.append('Just restart the app')
    what_to_do = ''
    ## If the repo is up to date, ask what to do
    if uptodate:
      what_to_do = prompt([{
        'type': 'list',
        'message': "The repository is already up to date. What should I do?",
        'name': 'what_to_do',
        'default': 'Nothing',
        'choices': what_to_do_choices
      }])['what_to_do']
      ## Exit
      if what_to_do == 'Nothing':
        return

    ## Pull from origin
    if not uptodate:
      git_pull()
      print('√ Pulled.')
    ## Do the steps
    if not uptodate or what_to_do == 'Do as if it was not up to date':
      update(steps)
    ## Restart (if the app is managed by pm2)
    if pm2:
      restart(pm2)
      print('√ Restarted.')


class working_dir:
  def __init__(self, path):
    self.path = path
    self.cwd = os.getcwd()
  def __enter__(self):
    os.chdir(self.path)
  def __exit__(self, type, value, traceback):
    os.chdir(self.cwd)

@yaspin(text="Checking for updates...")
def is_up_to_date():
  uptodate = shell('git log HEAD..origin/master --oneline', show=True).stdout == ''
  return uptodate

@yaspin(text="Pulling from origin...")
def git_pull():
  shell('git pull')
  # print("Done.")

@yaspin(text="Cloning repository...")
def git_clone(git_clone_url, dir_name):
  shell(f'git clone {git_clone_url} {dir_name}')

@yaspin(text="Restarting...")
def restart(pm2_app):
  shell(f'pm2 restart {pm2_app}')

def update(steps):
  for spinner_text, command in iterate_steps(steps):
    do_step(spinner_text+'...', command)

def do_step(text, command, **opts):
  @yaspin(text=text)
  def doit():
    shell(command, **opts)
  doit()
  print("√ " + _word_being_to_preterit(text, 'Done') + '.')

def iterate_steps(steps):
  for step in steps:
    for (verbose_name, command) in step.items():
      yield verbose_name, command

def _word_being_to_preterit(text: str, fallback: str):
  """
  Replaces the first word of :text: with its preterit tense, 
  or return :fallback:
  """
  REPLACE_MAP = {
    'Installing': 'Installed',
    'Building': 'Built',
    'Activating': 'Activated',
    'Copying': 'Copied',
    'Moving': 'Moved',
    'Compiling': 'Compiled',
    'Linting': 'Linted',
    'Stopping': 'Stopped',
    'Getting': 'Got',
    'Setting': 'Set',
    'Extracting': 'Extracted',
    'Restarting': 'Restarted',
    'Reloading': 'Reloaded',
    'Launching': 'Launched'
  }
  for (being, preterit) in REPLACE_MAP.items():
    if being in text.split(' '):
      return text.replace(being, preterit)
  return fallback

def shell(command, show=False):
  return run(command, shell=True, capture_output=not show)

if __name__ == "__main__":
  main()
