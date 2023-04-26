from datetime import date, timedelta
import json
import sys
import logging
from optapy import problem_fact, \
                    planning_id, \
                    planning_entity, \
                    planning_variable, \
                    constraint_provider, \
                    planning_solution, \
                    problem_fact_collection_property, \
                    value_range_provider, \
                    planning_entity_collection_property, \
                    planning_score, \
                    solver_manager_create, \
                    solver_factory_create

from optapy.types import Joiners, HardSoftScore, SolverConfig, Duration


@problem_fact
class WorkDay:
    def __init__(
            self,
            date):
        self.date = date

    @planning_id
    def get_ordinal(self):
        return self.date.toordinal()

    def __str__(self):
        return f"WorkDay(date={self.date.isoformat()})"


@problem_fact
class TeamMember:

    def __init__(
            self,
            id,
            name,
            profile,
            product):
        self.id = id
        self.name = name
        self.profile = profile
        self.product = product
        self.daysoff = []

    def add_day_off(
            self,
            year,
            month,
            day):
        self.daysoff.append(date(year, month, day))

    @planning_id
    def get_id(self):
        return self.id
    
    def get_name(self):
        return self.name

    def get_profile(self):
        return self.profile,

    def get_product(self):
        return self.product

    def __str__(self):
        return f"TeamMember(name={self.name}, profile={self.profile}, product={self.product}, daysoff={len(self.daysoff)})"


@planning_entity
class PlanningItem:

    def __init__(
            self,
            id,
            name,
            product,
            profile):
        self.id = id
        self.name = name
        self.product = product
        self.profile = profile
        self.work_day = None
        self.team_member = None

    @planning_id
    def get_id(self):
        return self.id

    @planning_variable(WorkDay, value_range_provider_refs=["WorkDays"])
    def get_work_day(self):
        return self.work_day

    def set_work_day(self, new_work_day):
        self.work_day = new_work_day

    @planning_variable(TeamMember, value_range_provider_refs=["TeamMembers"])
    def get_team_member(self):
        return self.team_member

    def set_team_member(self, new_team_member):
        self.team_member = new_team_member


@planning_solution
class TeamPlanning:
    def __init__(self, work_days, team_members, planning_items):
        self.work_days = work_days
        self.team_members = team_members
        self.planning_items = planning_items
        self.score = None

    @problem_fact_collection_property(WorkDay)
    @value_range_provider("WorkDays")
    def get_work_day_list(self):
        return self.work_days

    @problem_fact_collection_property(TeamMember)
    @value_range_provider("TeamMembers")
    def get_team_members(self):
        return self.team_members

    @planning_entity_collection_property(PlanningItem)
    def get_planning_items(self):
        return self.planning_items

    @planning_score(HardSoftScore)
    def get_score(self):
        return self.score

    def set_score(self, score):
        self.score = score


def penalize_all(constraint_factory):
    return constraint_factory \
        .for_each(PlanningItem) \
        .penalize("Penalize ALL !", HardSoftScore.ONE_HARD)


def team_member_capacity_per_day(constraint_factory):
    return constraint_factory \
        .for_each_unique_pair(PlanningItem,
            Joiners.equal(lambda item: item.work_day),
            Joiners.equal(lambda item: item.team_member)) \
        .penalize("Team member issue: Capacity", HardSoftScore.ONE_HARD)


def team_member_dedicated_to_product(constraint_factory):
    return constraint_factory \
        .for_each(PlanningItem) \
        .filter(lambda item: item.team_member.product != item.product) \
        .penalize("Team member issue: Product", HardSoftScore.ONE_HARD)


@constraint_provider
def planning_constraints( constraint_factory):
    result =  [
        # Hard constraints
        # penalize_all(constraint_factory)
        team_member_capacity_per_day(constraint_factory),
        team_member_dedicated_to_product(constraint_factory)
        # Soft constraints
    ]
    return result


class PlanningProblem:

    def __init__(self, file_path=None):
        self.team_members = []
        self.work_days = []
        self.planning_items = []
        if file_path is not None:
            self.load_from_json(file_path)
        

    def generate_work_days(self, iso_start_date, iso_end_date):

        current_date = date.fromisoformat(iso_start_date)
        end_date = date.fromisoformat(iso_end_date)

        while current_date.toordinal() <= end_date.toordinal():
            if current_date.isoweekday() < 6:  # Excluding week-end days
                self.work_days.append(WorkDay(current_date))
            current_date = current_date + timedelta(days=1)


    def load_from_json(self, file_path):

        with open(file_path, 'r') as file:
            json_content = file.read()
            problem_content = json.loads(json_content)

        self.generate_work_days(problem_content['workDayRange']['begin'], problem_content['workDayRange']['end'])

        # Load team members
        team_member_id = 0
        for team_member_def in problem_content['teamMembers']:
            self.team_members.append(TeamMember(
                team_member_id,
                team_member_def['name'],
                team_member_def['profile'],
                team_member_def['product']))
            team_member_id = team_member_id + 1
            
        # Generate planning items
        item_id = 0
        for epic_def in problem_content['epics']:
            for profile in epic_def['workloads'].keys():
                workload = epic_def['workloads'][profile]
                for d in range(workload):
                    self.planning_items.append(PlanningItem(
                        item_id,
                        epic_def['name'],
                        epic_def['product'],
                        profile))
                    item_id = item_id + 1

        
    def on_best_solution_changed(best_solution):
        print(best_solution)
  

    def solve(self, file_path):
        problem = TeamPlanning(self.work_days, self.team_members, self.planning_items)
        item = problem.planning_items[0]
        item.set_work_day(problem.work_days[0])
        item.set_team_member(problem.team_members[0])

        # logging.getLogger('optapy').setLevel(logging.DEBUG)

        solver_config = SolverConfig() \
            .withEntityClasses(PlanningItem) \
            .withSolutionClass(TeamPlanning) \
            .withConstraintProviderClass(planning_constraints) \
            .withTerminationSpentLimit(Duration.ofSeconds(30))

        solver = solver_factory_create(solver_config).buildSolver()
        solution = solver.solve(problem)
        
        with open(file_path, 'w') as file:
            file.write('date;product;epicName;profile;teamMember\n')
            for solution_item in solution.planning_items:
                file.write(f"{solution_item.work_day.date.isoformat()};{solution_item.product};{solution_item.name};{solution_item.profile};{solution_item.team_member.name}\n")


problem = PlanningProblem(sys.argv[1])
problem.solve(f"{sys.argv[1]}.solution.csv")
