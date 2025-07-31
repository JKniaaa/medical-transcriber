from invoke import task

@task
def hello(c):
    c.run("echo hello")


@task
def batch(c):
    c.run("streamlit run batch.py")


@task
def stream(c):
    c.run("streamlit run stream.py")


@task
def back(c):
    c.run("cd node-proxy && node server.js", env={"PYTHONUTF8": "1"})
