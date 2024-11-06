#!/usr/bin/env nextflow

nextflow.enable.dsl = 2

process subfits {
    container = params.COMBINATION_IMAGE
    containerOptions = "--bind ${params.SCRATCH_ROOT}:${params.SCRATCH_ROOT}"
    input:
        val image
        val output_image

    output:
        val output_image

    script:
        """
        python3 /app/src/subfits.py -i $image -o $output_image -r
        """
}

process miriad_combination_script {
    container = params.COMBINATION_IMAGE
    containerOptions = "--bind ${params.SCRATCH_ROOT}:${params.SCRATCH_ROOT}"
    input:
        val mwcombine_config
        val output_image

    output:
        val output_image

    script:
        """
        python3 /app/precombine.py -c $mwcombine_config
        """
}

process miriad {
    input:
        val script

    output:
        TBA

    script:
        """
        """
}

process source_finding {
    input:
        val image

    main:
        sofia()
        sofiax()
}

// ---------------------------------------------------------------------------------------

workflow milkyway {
    take:
        IMAGE

    main:
        subfits(IMAGE)
        single_dish_combination(subfits.out.image)
        source_finding(single_dish_combination.out.image)
}
