$(function() {
    const problemInstanceSelector = $('#id_problem_instance_id');
    problemInstanceSelector.on('change', function(event) {
        console.log(event.target.value);
    });
});
