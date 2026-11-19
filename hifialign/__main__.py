"""Command line / GUI entry point.

    python -m hifialign                       # open the graphical interface
    python -m hifialign gui [projet.hifi.json]
    python -m hifialign run projet1.hifi.json [projet2.hifi.json ...]   # batch, no GUI
"""
import argparse
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(prog='hifialign', description='HiFi multiplex image alignment')
    sub = ap.add_subparsers(dest='cmd')
    g = sub.add_parser('gui', help='open the graphical interface')
    g.add_argument('project', nargs='?')
    r = sub.add_parser('run', help='process one or several projects without GUI')
    r.add_argument('projects', nargs='+')
    r.add_argument('--register-only', action='store_true')
    r.add_argument('--write-only', action='store_true', help='reuse the transforms saved in the project')
    for p in (g, r):
        p.add_argument('--lang', choices=['fr', 'en'], help='interface / log language')
    args = ap.parse_args(argv)
    from .i18n import set_language, tr
    if getattr(args, 'lang', None):
        set_language(args.lang)
        if args.cmd == 'gui':
            from PySide6.QtCore import QSettings
            QSettings('UNIL', 'HiFiAlign').setValue('language', args.lang)

    if args.cmd == 'run':
        from .pipeline import Callbacks, Pipeline
        from .project import Project
        failed = 0
        for path in args.projects:
            print(f'===== {path}')
            proj = Project.load(path)

            def progress(stage, done, total):
                print(f'\r  {stage}: {done}/{total}', end='' if done < total else '\n', flush=True)

            try:
                outs = Pipeline(proj, Callbacks(log=print, progress=progress)).run(
                    do_register=not args.write_only, do_write=not args.register_only)
                for o in outs:
                    print('  ->', o)
                proj.save(path)   # keep the computed transforms in the project file
            except Exception as e:
                failed += 1
                print(tr('ERREUR : {e}', e=e), file=sys.stderr)
        return 1 if failed else 0

    from .gui.app import run_gui
    return run_gui(getattr(args, 'project', None))


if __name__ == '__main__':
    sys.exit(main())
