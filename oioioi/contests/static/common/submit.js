$(function() {
    const problemInstanceSelector = $("#id_problem_instance_id");
    problemInstanceSelector.on('change', function(event) {
        var problemInstanceId = event.target.value;

        const allFields = $("form [data-submit]");
        const customFields = $("form [data-submit='" + problemInstanceId + "']");
        if (customFields.length) {
            // found custom div
            allFields.parent().hide();
            customFields.parent().show();

            console.log("Set fields for problem " + problemInstanceId); // TODO remove debug
        } else {
            // custom div not found, fall back to default
            const defaultFields = $("form [data-submit='default']");
            allFields.parent().hide();
            defaultFields.parent().show();

            console.log("No custom fields for this problem instance"); // TODO remove debug
        }
    });
});
