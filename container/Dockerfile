FROM docker.io/openjdk:21-slim-bullseye

RUN apt update
RUN apt install python3-pip -y
RUN pip install optapy

ADD planning_problem_solver.py .

ENTRYPOINT ["python3", "planning_problem_solver.py"]