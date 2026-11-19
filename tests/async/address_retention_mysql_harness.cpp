// The hourly address prune (ADR 0003) on a real database. Runs the maintenance job with
// the given row budget until it reports complete, printing each run's outcome and rows.
// Arguments: host port user password database row-budget [time-budget-usec].
#include "persistence/maintenance_repository.h"
#include "persistence/persistence_observability.h"
#include "sql/sql_pool.h"

#include <cassert>
#include <cstdio>
#include <cstdlib>

static MYSQL *connection;

extern "C" MYSQL *sql_pool_acquire(void)
{
	return connection;
}

int main(int argc, char **argv)
{
	assert(argc == 7 || argc == 8);
	const uint64_t time_budget = argc == 8 ? strtoull(argv[7], nullptr, 10) : 0;
	connection = mysql_init(nullptr);
	assert(mysql_real_connect(connection, argv[1], argv[3], argv[4], argv[5], atoi(argv[2]),
				  nullptr, 0));
	for (uint64_t work = 1; work < 100; ++work)
	{
		maintenance_request request = {};
		request.work_id = work;
		request.job_id = maintenance_job_id::address_retention;
		request.row_budget = static_cast<uint32_t>(atoi(argv[6]));
		request.time_budget_usec = time_budget ? time_budget :
							 MAINTENANCE_TIME_BUDGET_USEC_MAX;
		// Like the scheduler, a given budget starts when the job runs. Without one, a
		// container's slow first queries get ten seconds.
		request.deadline_usec = persistence_observability_now_usec() +
					(time_budget ? time_budget : 10000000);
		const maintenance_result result = maintenance_repository_execute(request, nullptr);
		printf("%s %u\n",
		       result.outcome == maintenance_outcome::complete ? "complete" :
		       result.outcome == maintenance_outcome::more     ? "more" :
									 "failed",
		       result.rows);
		if (result.outcome != maintenance_outcome::more)
			return result.outcome == maintenance_outcome::complete ? 0 : 1;
	}
	return 1;
}
