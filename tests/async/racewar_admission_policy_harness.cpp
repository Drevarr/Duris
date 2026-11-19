#include "account/racewar_admission.h"

#include <climits>
#include <cstdlib>
#include <iostream>

static void require(bool condition, const char *message)
{
	if (!condition)
	{
		std::cerr << message << '\n';
		exit(1);
	}
}

int main()
{
	constexpr long now = 10'000;
	constexpr long configured_cooldown = 913;

	auto result = account_racewar_evaluate(ACCOUNT_RACEWAR_EVIL, false,
					       now - configured_cooldown + 1, 0, now,
					       configured_cooldown);
	require(!result.allowed && result.denial == ACCOUNT_RACEWAR_DENIAL_COOLDOWN &&
			result.remaining_seconds == 1,
		"Good-to-Evil was not denied exactly one second before expiry");

	result = account_racewar_evaluate(ACCOUNT_RACEWAR_EVIL, false, now - configured_cooldown, 0,
					  now, configured_cooldown);
	require(result.allowed && result.remaining_seconds == 0,
		"Good-to-Evil was not allowed exactly at expiry");

	result = account_racewar_evaluate(ACCOUNT_RACEWAR_GOOD, false, 0,
					  now - configured_cooldown + 37, now, configured_cooldown);
	require(!result.allowed && result.remaining_seconds == 37,
		"Evil-to-Good did not use the configured cooldown");

	result = account_racewar_evaluate(ACCOUNT_RACEWAR_GOOD, false, now - 1, 0, now,
					  configured_cooldown);
	require(result.allowed, "same-side Good admission was denied");
	result = account_racewar_evaluate(ACCOUNT_RACEWAR_EVIL, false, 0, now - 1, now,
					  configured_cooldown);
	require(result.allowed, "same-side Evil admission was denied");

	result = account_racewar_evaluate(ACCOUNT_RACEWAR_EXEMPT, false, now, now, now,
					  configured_cooldown);
	require(result.allowed, "trusted admission did not retain its exemption");
	result = account_racewar_evaluate(ACCOUNT_RACEWAR_EXEMPT, true, now, now, now,
					  configured_cooldown);
	require(!result.allowed && result.denial == ACCOUNT_RACEWAR_DENIAL_BLOCKED,
		"a blocked trusted character bypassed the character block");

	result = account_racewar_evaluate(ACCOUNT_RACEWAR_UNRESTRICTED, false, now, now, now,
					  configured_cooldown);
	require(result.allowed, "an unrestricted racewar side was denied");
	result = account_racewar_evaluate(ACCOUNT_RACEWAR_GOOD, false, 0, now + 5, now,
					  configured_cooldown);
	require(!result.allowed && result.remaining_seconds == configured_cooldown + 5,
		"future timestamps were not handled conservatively");
	result = account_racewar_evaluate(ACCOUNT_RACEWAR_GOOD, false, 0, LONG_MAX, LONG_MIN,
					  configured_cooldown);
	require(!result.allowed && result.remaining_seconds == LONG_MAX,
		"future timestamp arithmetic did not saturate");

	result = account_racewar_pending_switch(0, 0, now, configured_cooldown);
	require(result.remaining_seconds == 0, "a fresh account reported a side-switch wait");
	result = account_racewar_pending_switch(0, now - 100, now, configured_cooldown);
	require(result.side == ACCOUNT_RACEWAR_GOOD &&
			result.remaining_seconds == configured_cooldown - 100,
		"the wait after playing Evil did not name Good");
	result = account_racewar_pending_switch(now - 100, 0, now, configured_cooldown);
	require(result.side == ACCOUNT_RACEWAR_EVIL &&
			result.remaining_seconds == configured_cooldown - 100,
		"the wait after playing Good did not name Evil");
	result = account_racewar_pending_switch(now - configured_cooldown, 0, now,
						configured_cooldown);
	require(result.remaining_seconds == 0, "an expired side-switch wait was still reported");
	// Both sides wait when the cooldown outlasts the switch; the later side was played last.
	result = account_racewar_pending_switch(now - 100, now - 200, now, configured_cooldown);
	require(result.side == ACCOUNT_RACEWAR_EVIL &&
			result.remaining_seconds == configured_cooldown - 100,
		"the wait did not follow the side played last (Good)");
	result = account_racewar_pending_switch(now - 200, now - 100, now, configured_cooldown);
	require(result.side == ACCOUNT_RACEWAR_GOOD &&
			result.remaining_seconds == configured_cooldown - 100,
		"the wait did not follow the side played last (Evil)");

	std::cout << "racewar admission policy tests passed\n";
	return 0;
}
