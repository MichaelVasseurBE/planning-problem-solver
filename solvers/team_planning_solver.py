from datetime import date, timedelta
import json
import sys
import logging
from optapy import problem_fact, \
                    planning_id, \
                    planning_entity, \
                    planning_variable, \
                    inverse_relation_shadow_variable, \
                    constraint_provider, \
                    planning_solution, \
                    problem_fact_collection_property, \
                    value_range_provider, \
                    planning_entity_collection_property, \
                    planning_score, \
                    solver_manager_create, \
                    solver_factory_create

from optapy.types import Joiners, HardSoftScore, SolverConfig, Duration

from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication




@planning_entity
class WorkDay:
    def __init__(
            self,
            id,
            date):
        self.id = id
        self.date = date
        self.planned_items = []
        
    @planning_id
    def get_id(self):
        return self.id

    def __str__(self):
        return f"WorkDay(date={self.date.isoformat()})"


@problem_fact
class TeamMember:

    def __init__(
            self,
            id,
            name,
            profile,
            product,
            daysoff):
        self.id = id
        self.name = name
        self.profile = profile
        self.product = product
        self.daysoff = daysoff

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
            epic,
            priority,
            dead_line,
            product,
            profile):
        self.id = id
        self.epic = epic
        self.priority = priority
        self.dead_line = dead_line
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

    def __str__(self):
        return f"PlanningItem(work_day={self.work_day}, team_member={self.team_member}, product={self.product}, profile={self.profile} )"

    def bad_profile_assignment(self):
        return self.team_member.profile != '*' and self.team_member.profile != self.profile

    def bad_product_assignment(self):
        return self.team_member.product != '*' and self.team_member.product != self.product
    
    def bad_day_assignment(self):
        return self.work_day.date.isoformat() in self.team_member.daysoff
    
    def dead_line_fail(self):
        return False if self.dead_line is None else self.work_day.date.toordinal() > date.fromisoformat(self.dead_line).toordinal()


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

    def csv_output(self):
        sorted_items = sorted(self.planning_items, key=lambda item: (item.product, item.epic))
        print('date;product;epicName;profile;teamMember')
        for item in sorted_items:
            print(f"{item.work_day.date.isoformat()};{item.product};{item.epic};{item.profile};{item.team_member.name}")        

    def consolidate_planning_per_product(self):
        sorted_items = sorted(self.planning_items, key=lambda item: (item.product, item.epic))
        consolidated_planning = {}
        for item in sorted_items:
            # Update product
            if item.product not in consolidated_planning.keys():
                consolidated_planning[item.product] = {}
            product_item = consolidated_planning[item.product]

            # Update epic
            if item.epic not in product_item:
                product_item[item.epic] = {}
            epic_item = product_item[item.epic]
            if 'beginDate' not in epic_item or item.work_day.date.toordinal() < epic_item['beginDate'].toordinal():
                epic_item['beginDate'] = item.work_day.date
            if 'endDate' not in epic_item or item.work_day.date.toordinal() > epic_item['endDate'].toordinal():
                epic_item['endDate'] = item.work_day.date

        return consolidated_planning
    
    def mermaid_gantt_output_per_product_and_epic(self, title):
        planning = self.consolidate_planning_per_product()

        print('gantt')
        print(f"\ttitle {title} - Products & Epics")
        print(f"\tdateFormat YYYY-MM-DD")

        for product in planning.keys():
            print(f"\tsection {product}")
            for epic in planning[product].keys():
                print(f"\t{epic}\t:{planning[product][epic]['beginDate'].isoformat()}, {planning[product][epic]['endDate'].isoformat()}")    
    
    def consolidate_planning_per_member(self):
        sorted_items = sorted(self.planning_items, key=lambda item: (item.product, item.epic))
        consolidated_planning = {}
        for item in sorted_items:
            # Update member
            if item.team_member.name not in consolidated_planning.keys():
                consolidated_planning[item.team_member.name] = {}
            member_item = consolidated_planning[item.team_member.name]

            # Update workload
            workload = f"{item.epic} ({item.profile})"
            if workload not in member_item:
                member_item[workload] = {}
            workload_item = member_item[workload]
            if 'beginDate' not in workload_item or item.work_day.date.toordinal() < workload_item['beginDate'].toordinal():
                workload_item['beginDate'] = item.work_day.date
            if 'endDate' not in workload_item or item.work_day.date.toordinal() > workload_item['endDate'].toordinal():
                workload_item['endDate'] = item.work_day.date

        return consolidated_planning
        
    def mermaid_gantt_output_per_member_and_workload(self, title):
        planning = self.consolidate_planning_per_member()

        print('gantt')
        print(f"\ttitle {title} - Members & Workloads")
        print(f"\tdateFormat YYYY-MM-DD")

        for member in planning.keys():
            print(f"\tsection {member}")
            for workload in planning[member].keys():
                print(f"\t{workload}\t:{planning[member][workload]['beginDate'].isoformat()}, {planning[member][workload]['endDate'].isoformat()}")

def penalize_all(constraint_factory):
    return constraint_factory \
        .for_each(PlanningItem) \
        .penalize("Penalize ALL !", HardSoftScore.ONE_HARD)

def team_member_capacity_per_day(constraint_factory):
    return constraint_factory \
        .for_each(PlanningItem) \
        .join(PlanningItem, \
            Joiners.equal(lambda item: item.work_day), \
            Joiners.equal(lambda item: item.team_member), \
            Joiners.less_than(lambda item: item.id) \
        ) \
        .penalize("Team member issue: Capacity", HardSoftScore.ONE_HARD)

def team_member_has_a_profile(constraint_factory):
    return constraint_factory \
        .for_each(PlanningItem) \
        .filter(lambda item: item.bad_profile_assignment()) \
        .penalize("Team member issue: Profile", HardSoftScore.ONE_HARD)

def team_member_assigned_to_a_product(constraint_factory):
    return constraint_factory \
        .for_each(PlanningItem) \
        .filter(lambda item: item.bad_product_assignment()) \
        .penalize("Team member issue: Product", HardSoftScore.ONE_HARD)

def team_member_has_days_off(constraint_factory):
    return constraint_factory \
        .for_each(PlanningItem) \
        .filter(lambda item: item.bad_day_assignment()) \
        .penalize("Team member issue: Day Off", HardSoftScore.ONE_HARD)

def qa_cannot_be(constraint_factory):
    return constraint_factory \
        .for_each(PlanningItem) \
        .filter(lambda item: item.bad_day_assignment()) \
        .penalize("Team member issue: Day Off", HardSoftScore.ONE_HARD)


def enforce_dead_lines(constraint_factory):
    return constraint_factory \
        .for_each(PlanningItem) \
        .filter(lambda item: item.dead_line_fail()) \
        .penalize("Dead line fail", HardSoftScore.ONE_HARD)

def focused_team_member(constraint_factory):
    return constraint_factory \
        .for_each(PlanningItem) \
        .join(PlanningItem, \
            Joiners.equal(lambda item: item.team_member), \
            Joiners.less_than(lambda item: item.id) \
        ) \
        .filter(lambda item1, item2: item1.epic != item2.epic) \
        .penalize("Team member issue: Focus", HardSoftScore.ONE_SOFT)

def enforce_epic_priority(constraint_factory):
    return constraint_factory \
        .for_each(PlanningItem) \
        .penalize("Epic priority", HardSoftScore.ONE_SOFT, lambda item: item.priority)

@constraint_provider
def planning_constraints( constraint_factory):
    result =  [
        # Hard constraints
        team_member_capacity_per_day(constraint_factory),
        team_member_assigned_to_a_product(constraint_factory),
        team_member_has_a_profile(constraint_factory),
        team_member_has_days_off(constraint_factory),
        # enforce_dead_lines(constraint_factory),
        # focused_team_member(constraint_factory),env
        # enforce_epic_priority(constraint_factory)

        # Soft constraints
    ]
    return result


class PlanningProblem:

    def __init__(self, args):
        self.team_members = []
        self.work_days = []
        self.planning_items = []

        if args[1] == 'json' and len(args) == 3:
            self.load_from_json(args[2])
        elif args[1] == 'azureDevOps' and len(args) == 5:
            self.load_from_azure_devops(args[2], args[3], args[4])
        

    def generate_work_days(self, iso_start_date, iso_end_date, team_days_off):

        current_date = date.fromisoformat(iso_start_date)
        end_date = date.fromisoformat(iso_end_date)
        workday_id = 0

        while current_date.toordinal() <= end_date.toordinal():
             # Excluding week-end days and public holidays
            if current_date.isoweekday() < 6 and current_date.isoformat() not in team_days_off:
                self.work_days.append(WorkDay(workday_id, current_date))
                workday_id = workday_id + 1
            current_date = current_date + timedelta(days=1)

    def load_from_azure_devops(self, organization_url, personal_access_token, project_name):
        credentials = BasicAuthentication('', personal_access_token)
        connection = Connection(base_url=organization_url, creds=credentials)
        core_client = connection.clients.get_core_client()
        project = core_client.get_project(project_name)
        print(project.__dict__)


    def load_from_json(self, file_path):

        with open(file_path, 'r') as file:
            json_content = file.read()
            problem_content = json.loads(json_content)

        self.title = problem_content['title']

        self.generate_work_days(problem_content['workDayRange']['begin'], problem_content['workDayRange']['end'], problem_content['workDayRange']['teamDaysOff'])

        # Load team members
        team_member_id = 0
        for team_member_def in problem_content['teamMembers']:
            self.team_members.append(TeamMember(
                team_member_id,
                team_member_def['name'],
                team_member_def['profile'],
                team_member_def['product'],
                team_member_def['daysOff']))
            team_member_id = team_member_id + 1

        # sorting epics by priorities
            
        # Generate planning items
        item_id = 0
        for epic_def in problem_content['epics']:
            for profile in epic_def['workloads'].keys():
                workload = epic_def['workloads'][profile]
                for d in range(workload):
                    self.planning_items.append(PlanningItem(
                        item_id,
                        epic_def['name'],
                        epic_def.get('priority', 10),
                        epic_def.get('deadLine'),
                        epic_def['product'],
                        profile))
                    item_id = item_id + 1
        

    def solve(self):
        print(f"Solving {self.title} ...")

        problem = TeamPlanning(self.work_days, self.team_members, self.planning_items)
        item = problem.planning_items[0]
        item.set_work_day(problem.work_days[0])
        item.set_team_member(problem.team_members[0])

        # logging.getLogger('optapy').setLevel(logging.DEBUG)

        solver_config = SolverConfig() \
            .withEntityClasses(PlanningItem) \
            .withSolutionClass(TeamPlanning) \
            .withConstraintProviderClass(planning_constraints) \
            .withTerminationSpentLimit(Duration.ofSeconds(5))

        solver = solver_factory_create(solver_config).buildSolver()
        solution = solver.solve(problem)
        return solution


problem = PlanningProblem(sys.argv)
solution = problem.solve() # f"{sys.argv[1]}.solution.csv")
print(f"Final score : {solution.score.toString() if solution.score is not None else 'N/A'}")
print(f"CSV OUTPUT")
solution.csv_output()
print(f"PRODUCT/EPIC GANTT")
solution.mermaid_gantt_output_per_product_and_epic(problem.title)
print(f"MEMBER/WORKLOAD GANTT")
solution.mermaid_gantt_output_per_member_and_workload(problem.title)
