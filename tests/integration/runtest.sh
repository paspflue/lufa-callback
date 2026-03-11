#!/bin/bash


rm *.actual
for file in *.yml; do
	ansible-playbook --extra-vars tower_job_id=123 "$file"
	mv out.txt "$file.actual"
done

echo "##### Test Results ####"
echo ""

num_failed=0

for file in *.yml; do
	if diff -q "$file.expected" "$file.actual"
	then
		echo -e "$file \e[32mpass\e[0m"
	else
		echo -e "$file \e[31mFAILED\e[0m"
		let num_failed++
	fi
done
exit $num_failed
